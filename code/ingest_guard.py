# -*- coding: utf-8 -*-
"""ingest_guard.py — TẦNG NHẬN DỮ LIỆU & TỰ FALLBACK (đặc tả: docs/07 §6c).

Chạy TRƯỚC mọi thuật toán thiên văn:

  Lớp A  hợp đồng metadata (stage, hardware_id, adc_bits, sample_rate_hz,
         center_freq_hz, calibrated*, time_sync, telemetry). Thiếu thì suy ra
         và đánh dấu, KHÔNG im lặng dùng mặc định.
  Lớp B  nhận dạng MÙ theo nội dung (không dựa vào đuôi file): complex/âm →
         RAW_IQ; thực P≥0 → CHANNELIZED_POWER, chia nhánh theo Δt; vòm bandpass
         > 3 dB → flatten + edge_zap; phẳng 0 dB → TẮT flatten; đỉnh giữa băng
         → DC notch; có gap → xử lý theo đoạn; LOCAL_CLOCK → mở rộng dải tìm P.
  Gatekeeper  bão hoà ADC · radiometer · spectral kurtosis · nhiệt độ/T_sys.
  Tagging  VALID / RFI_HEAVY / GAIN_DRIFT / SATURATED / SPECTRUM_1D / CORRUPTED.

Bốn quy tắc I/O bắt buộc (chạy thực chiến 4–5 h, dữ liệu hàng chục GB):
  Q1  chỉ đọc 3 lát (đầu/giữa/cuối), tối đa vài MB — không bao giờ nạp cả file;
  Q2  kiểm tra ổ đĩa trước khi ghi + ghi JSON nguyên tử (.tmp → os.replace);
  Q3  làm sạch NaN/Inf (nội suy nếu < 0,1 %, cờ CORRUPTED nếu > 1 %); hỗ trợ
      dấu phẩy thập phân khi phân cách là ';' hoặc tab;
  Q4  dữ liệu thô là CHỈ ĐỌC; lưu input_sha256 + schema_version để truy vết.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil

import numpy as np

STAGES = ("RAW_IQ", "CHANNELIZED_POWER", "DEDISPERSED_TS")
TIME_SYNCS = ("GPS_PPS", "NTP", "LOCAL_CLOCK")

ADC_WARN = 0.0001          # 0,01 %
ADC_ABORT = 0.005          # 0,5 %
RADIOMETER_TOL = 0.20      # lệch 20 %
SK_SIGMA = 3.0
TSYS_FACTOR = 1.5
DT_LNA_LIMIT = 2.0         # °C
DT_PULSAR_MAX = 1e-3       # s
DT_HI_MIN = 10e-3          # s
NAN_REPAIR = 0.001         # < 0,1 % → nội suy
NAN_CORRUPT = 0.01         # > 1 % → CORRUPTED

MAX_SNIFF_BYTES = 8_000_000
SNIFF_SLICES = ("head", "mid", "tail")
DISK_MARGIN = 1.2
DISK_MIN_FREE_MB = 500

_DT_MAP = {"ci8": np.int8, "cu8": np.uint8, "ci16": np.int16, "cu16": np.uint16,
           "ci32": np.int32, "cu32": np.uint32, "cf32": np.complex64,
           "cf64": np.complex128, "ri16": np.int16, "ru8": np.uint8}
_BITS_MAP = {"ci8": 8, "cu8": 8, "ci16": 16, "cu16": 16, "ci32": 32,
             "cu32": 32, "ri16": 16, "ru8": 8}


# ============================================================ Q1–Q4: I/O
def input_fingerprint(path: str, head_bytes: int = 64 << 20) -> dict:
    """Q4 — dấu vân tay file vào (64 MB đầu + kích thước). File mở CHỈ ĐỌC."""
    out = dict(sha256_head=None, size=0, mtime=None, hashed_bytes=0)
    try:
        st = os.stat(path)
        out["size"], out["mtime"] = st.st_size, int(st.st_mtime)
        h = hashlib.sha256()
        with open(path, "rb") as fh:
            left = head_bytes
            while left > 0:
                b = fh.read(min(1 << 20, left))
                if not b:
                    break
                h.update(b)
                left -= len(b)
        out["sha256_head"] = h.hexdigest()
        out["hashed_bytes"] = min(head_bytes, st.st_size)
    except Exception as exc:                     # noqa: BLE001
        out["error"] = repr(exc)
    return out


def disk_preflight(path_dir: str, need_bytes: float) -> dict:
    """Q2 — kiểm tra dung lượng TRƯỚC khi ghi (ước lượng × 1,2)."""
    try:
        os.makedirs(path_dir, exist_ok=True)
        free = shutil.disk_usage(path_dir).free
    except Exception as exc:                     # noqa: BLE001
        return dict(ok=False, free=0, need=int(need_bytes), error=repr(exc))
    need = int(need_bytes * DISK_MARGIN)
    ok = (free - need) > DISK_MIN_FREE_MB * 1024 * 1024 or need < 100 * 1024 * 1024
    return dict(ok=bool(ok), free=int(free), need=need, margin=DISK_MARGIN,
                min_free_mb=DISK_MIN_FREE_MB)


def atomic_write_json(path: str, obj) -> None:
    """Q2 — ghi qua .tmp rồi os.replace: mất điện không để lại JSON cụt."""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=2)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def sanitize_nonfinite(arr, name: str = "data") -> tuple:
    """Q3 — NaN/Inf: < 0,1 % nội suy; > 1 % → CORRUPTED (không dùng được)."""
    a = np.asarray(arr, dtype=float)
    if a.size == 0:
        return a, dict(frac=0.0, replaced=0, tag="OK", name=name)
    bad = ~np.isfinite(a)
    frac = float(np.mean(bad))
    rep = dict(frac=round(frac, 6), replaced=0, tag="OK", name=name)
    if frac == 0.0:
        return a, rep
    if frac > NAN_CORRUPT:
        rep.update(tag="CORRUPTED",
                   note=f"{frac*100:.2f} % mẫu không hữu hạn (>1 %) → loại")
        return a, rep
    clean = a.copy()
    if a.ndim == 2:
        for j in range(a.shape[1]):
            col = clean[:, j]
            badc = ~np.isfinite(col)
            if not badc.any():
                continue
            good = np.isfinite(col)
            if good.sum() >= 2:
                col[badc] = np.interp(np.where(badc)[0], np.where(good)[0], col[good])
            else:
                col[badc] = 0.0
            clean[:, j] = col
    else:
        good = np.isfinite(a)
        if good.sum() >= 2:
            clean[~good] = np.interp(np.where(~good)[0], np.where(good)[0], a[good])
        else:
            clean[~good] = 0.0
    rep.update(replaced=int(bad.sum()), tag="REPAIRED",
               note=f"{frac*100:.3f} % mẫu không hữu hạn → nội suy {int(bad.sum())} điểm")
    return clean, rep


def _inside(path: str, parent: str) -> bool:
    """True nếu path nằm trong parent (an toàn khi khác ổ đĩa Windows)."""
    try:
        return os.path.commonpath([os.path.abspath(path),
                                   os.path.abspath(parent)]) == os.path.abspath(parent)
    except ValueError:                # khác ổ đĩa → chắc chắn không nằm trong
        return False


def refuse_write_into_raw(target: str, raw_dir: str) -> None:
    """Q4 — không bao giờ ghi vào thư mục dữ liệu thô."""
    if _inside(target, raw_dir):
        raise PermissionError(
            f"từ chối ghi vào thư mục dữ liệu thô ({raw_dir}): dữ liệu gốc là "
            f"chỉ đọc, kết quả phải nằm trong results/")


# ============================================================ Lớp A
def validate_metadata(meta: dict | None) -> dict:
    """Kiểm hợp đồng metadata; trả present/missing/problems/complete."""
    meta = dict(meta or {})
    need = ("stage", "hardware_id", "adc_bits", "sample_rate_hz",
            "center_freq_hz", "time_sync")
    missing = [k for k in need if meta.get(k) in (None, "")]
    problems = []
    if meta.get("stage") and meta["stage"] not in STAGES:
        problems.append(f"stage lạ: {meta['stage']}")
    if meta.get("time_sync") and meta["time_sync"] not in TIME_SYNCS:
        problems.append(f"time_sync lạ: {meta['time_sync']}")
    if "calibrated" in meta and not any(
            k in meta for k in ("bandpass_flattened", "flux_calibrated", "tsys_known")):
        meta["bandpass_flattened"] = bool(meta["calibrated"])
    for k in ("bandpass_flattened", "flux_calibrated", "tsys_known"):
        meta.setdefault(k, None)
    return dict(meta=meta, missing=missing, problems=problems,
                complete=not missing and not problems)


# ============================================================ đọc bảng text
_NUM = re.compile(r"^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$")
_SPECIAL = {"nan", "na", "n/a", "-", "inf", "+inf", "-inf", "infinity"}


def _norm(tok: str) -> str:
    return tok.strip().replace(",", ".")


def _is_num(tok: str) -> bool:
    t = _norm(tok)
    return t.lower() in _SPECIAL or bool(_NUM.match(t))


def _to_float(tok: str) -> float:
    t = _norm(tok)
    return float("nan") if t.lower() in _SPECIAL else float(t)


def read_table_text(path: str, max_lines: int = 5000,
                    max_bytes: int = 4_000_000) -> dict:
    """Đọc CSV/TSV/space: TỰ BỎ header text, giữ NaN, phân biệt 1D/2D."""
    out = dict(kind="unknown", ncol=0, nrow=0, header_lines=0, delimiter=None,
               rows=None, freq_axis=None, time_axis=None, problems=[],
               truncated=False, n_header_text=0)
    size = os.path.getsize(path)
    with open(path, "rb") as fh:                 # CHỈ ĐỌC, có giới hạn
        raw = fh.read(min(size, max_bytes))
    out["truncated"] = size > len(raw)
    if bytes([0]) in raw[:4096]:
        out["problems"].append("có byte NUL → không phải file text")
        return out
    text = raw.decode("utf-8", "replace")
    lines = [ln.rstrip("\r") for ln in text.split("\n")]

    start, delim = None, None
    for i, ln in enumerate(lines[:3000]):
        if not ln.strip() or ln.lstrip().startswith(("#", "%", "//", ";")):
            continue
        for d in (",", "\t", ";", None):
            toks = [t for t in (ln.split(d) if d else ln.split()) if t.strip()]
            if toks and sum(_is_num(t) for t in toks) >= max(1, 0.6 * len(toks)):
                start, delim = i, d
                break
        if start is not None:
            break
    if start is None:
        out["problems"].append("không thấy dòng số nào (không phải bảng)")
        return out
    out["header_lines"] = start
    out["n_header_text"] = sum(1 for ln in lines[:start] if ln.strip())
    out["delimiter"] = {",": "comma", "\t": "tab", ";": "semicolon",
                        None: "space"}[delim]

    rows = []
    for ln in lines[start:]:
        if not ln.strip():
            continue
        toks = [t for t in (ln.split(delim) if delim else ln.split()) if t.strip()]
        if not toks or sum(_is_num(t) for t in toks) < 0.6 * len(toks):
            break                                # footer / chú thích
        try:
            rows.append([_to_float(t) for t in toks if _is_num(t)])
        except ValueError:
            break
        if len(rows) >= max_lines:
            out["truncated"] = True
            break
    if not rows:
        out["problems"].append("không đọc được dòng số")
        return out
    ncol = min(len(r) for r in rows)
    arr = np.array([r[:ncol] for r in rows], dtype=float)
    out.update(rows=arr, nrow=int(arr.shape[0]), ncol=int(ncol))

    if ncol <= 2:
        out["kind"] = "spectrum_1d"
        x = arr[:, 0]
        if ncol == 2 and (np.all(np.diff(x) > 0) or np.all(np.diff(x) < 0)):
            out["freq_axis"] = x
    else:
        out["kind"] = "matrix_2d"
        x = arr[:, 0]
        if np.all(np.diff(x) > 0) or np.all(np.diff(x) < 0):
            out["time_axis"] = x
    return out


# ============================================================ container
def sniff_format(path: str) -> dict:
    """Nhận dạng CONTAINER bằng magic bytes (trước khi đoán dtype)."""
    out = dict(kind="unknown", stage=None, datatype=None, detail="")
    try:
        with open(path, "rb") as fh:
            head = fh.read(512)
    except Exception as exc:                     # noqa: BLE001
        out["detail"] = repr(exc)
        return out
    low = path.lower()
    if head[:6] == b"SIMPLE":
        return dict(out, kind="psrfits", stage="CHANNELIZED_POWER", detail="PSRFITS")
    if b"HEADER_START" in head:
        return dict(out, kind="sigproc", stage="CHANNELIZED_POWER",
                    detail="SIGPROC filterbank")
    if head[:4] == b"RIFF":
        return dict(out, kind="wav", stage="RAW_IQ", detail="WAV")
    if low.endswith(".sigmf-data"):
        dt = None
        mp = path[:-len(".sigmf-data")] + ".sigmf-meta"
        if os.path.exists(mp):
            try:
                with open(mp, encoding="utf-8") as fh:
                    g = (json.load(fh).get("global") or {})
                dt = g.get("core:datatype") or g.get("datatype")
                out["detail"] = f"SigMF ({dt})"
            except Exception:                    # noqa: BLE001
                pass
        return dict(out, kind="sigmf", stage="RAW_IQ", datatype=dt)
    try:
        head.decode("utf-8")
        if bytes([0]) not in head:
            return dict(out, kind="text", detail="text/CSV")
    except Exception:                            # noqa: BLE001
        pass
    return dict(out, kind="binary", detail="nhị phân không rõ container")


def _dtype_of(datatype: str | None):
    key = (datatype or "").lower().replace("_le", "").replace("_be", "")
    return key, _DT_MAP.get(key), _BITS_MAP.get(key)


def read_raw_at(path: str, dtype, offset_bytes: int, max_items: int):
    """Q1 — đọc tối đa max_items mẫu TẠI offset (không nạp cả file)."""
    try:
        with open(path, "rb") as fh:
            fh.seek(max(0, int(offset_bytes)))
            return np.fromfile(fh, dtype=dtype, count=int(max_items))
    except Exception:                            # noqa: BLE001
        return np.array([])


def read_sample_slices(path: str, fmt: dict, bytes_each: int = 2_000_000) -> dict:
    """Q1 — 3 lát đầu/giữa/cuối; mỗi lát ≤ bytes_each."""
    size = os.path.getsize(path)
    _, dt, _ = _dtype_of(fmt.get("datatype"))
    if dt is None:
        dt = np.int8
    items = max(1000, bytes_each // np.dtype(dt).itemsize)
    offs = {"head": 0, "mid": size // 2, "tail": max(0, size - bytes_each)}
    out = {}
    for k, off in offs.items():
        out[k] = read_raw_at(path, dt, off, items)
    out["dtype"] = str(np.dtype(dt))
    out["size"] = size
    return out


# ============================================================ Lớp B
def _median_spectrum(x) -> np.ndarray:
    a = np.asarray(x, dtype=float)
    return a if a.ndim == 1 else np.median(a, axis=0)


def fingerprint(sample, tsamp_s: float | None = None,
                meta: dict | None = None) -> dict:
    """Nhận dạng mù trên mẫu (0,1–1 s hoặc một khung phổ)."""
    meta = dict(meta or {})
    actions, warnings, metrics = [], [], {}
    a = np.asarray(sample)
    is_complex = np.iscomplexobj(a)
    neg = float(np.mean(a.real < 0)) if a.size else 0.0
    metrics.update(is_complex=bool(is_complex), neg_frac=round(neg, 4),
                   dtype=str(a.dtype))
    hint = meta.get("stage")
    if hint in STAGES:
        stage = hint
    elif is_complex or (a.ndim == 1 and neg > 0.05):
        stage = "RAW_IQ"
    else:
        stage = "CHANNELIZED_POWER"
    if stage == "RAW_IQ":
        actions.append("fft")
    if a.size and not is_complex and float(np.min(a)) < -1e-6 and stage != "RAW_IQ":
        warnings.append("dữ liệu thực nhưng có giá trị âm — có thể đã trừ nền")
    metrics["stage"] = stage

    if stage == "CHANNELIZED_POWER" and tsamp_s:
        metrics["tsamp_s"] = tsamp_s
        if tsamp_s <= DT_PULSAR_MAX:
            actions.append("route:pulsar")
        elif tsamp_s > DT_HI_MIN:
            actions.append("route:hi_continuum")
        else:
            warnings.append(f"Δt = {tsamp_s*1e3:.1f} ms giữa 1–10 ms: quá chậm cho "
                            f"pulsar, quá nhanh cho HI")

    if stage != "RAW_IQ" and a.size:
        spec = _median_spectrum(a)
        if spec.size >= 16:
            n = spec.size
            e = max(1, int(0.10 * n))
            edge = float(np.median(np.r_[spec[:e], spec[-e:]]))
            centre = float(np.median(spec[int(0.2 * n):int(0.8 * n)]))
            ratio = edge / centre if centre > 0 else 0.0
            flat = float(np.std(spec) / (abs(np.mean(spec)) + 1e-12))
            metrics.update(edge_ratio=round(ratio, 4), flatness=round(flat, 6))
            if centre <= 0:
                warnings.append("phổ toàn 0 hoặc âm — dữ liệu chết?")
                metrics["bandpass"] = "dead"
            elif ratio < 0.707:
                actions += ["flatten", "edge_zap"]
                metrics["bandpass"] = "uncalibrated_bow"
            elif flat < 1e-6:
                actions.append("edge_zap")
                metrics["bandpass"] = "dead"
                warnings.append("phổ phẳng tuyệt đối — kiểm tra dữ liệu chết")
            else:
                actions.append("no_flatten")
                metrics["bandpass"] = "flat"
            dc = float(spec[n // 2] / (np.median(spec) + 1e-12))
            metrics["dc_ratio"] = round(dc, 2)
            if dc > 3.0:
                actions.append("dc_notch")
                if dc > 10.0:
                    warnings.append(f"đỉnh DC rất mạnh ({dc:.0f}× trung vị)")

    gaps = meta.get("gaps") or []
    if gaps:
        actions.append("segments")
        metrics["n_gaps"] = len(gaps)
        warnings.append(f"có {len(gaps)} khoảng mất mẫu → xử lý theo đoạn")
    if meta.get("time_sync") == "LOCAL_CLOCK":
        actions.append("widen_period_search")
        warnings.append("LOCAL_CLOCK: trôi ~1–2 ppm; với P < 10 ms phải có PPS/NTP")
    return dict(stage=stage, actions=sorted(set(actions)), metrics=metrics,
                warnings=warnings)


# ============================================================ Gatekeeper
def adc_clipping(x, bits: int = 8) -> dict:
    """Tỷ lệ mẫu chạm ngưỡng + chuỗi bão hoà dài nhất."""
    a = np.asarray(x)
    if a.size == 0:
        return dict(frac=0.0, max_run=0, tag="OK", limit=0.0, bits=bits)
    if np.iscomplexobj(a):
        mag = np.maximum(np.abs(a.real), np.abs(a.imag))
    else:
        mag = np.abs(a).astype(float)
    mag = np.ravel(mag)          # mảng 2 chiều (kênh × thời gian) → 1 chiều
    full = float(2 ** (int(bits) - 1)) if bits else float(np.max(mag) or 1.0)
    hot = mag >= full * 0.985
    frac = float(np.mean(hot))
    run = best = 0
    for h in hot[:200000]:
        run = run + 1 if h else 0
        best = max(best, run)
    tag = "ABORT" if frac > ADC_ABORT else ("WARN" if frac > ADC_WARN else "OK")
    return dict(frac=round(frac, 6), max_run=int(best), tag=tag,
                limit=full, bits=int(bits))


def radiometer_check(power, df_hz: float, dt_s: float) -> dict:
    """σ/μ mỗi kênh so với 1/√(Δf·τ) (dùng độ phân giải, không phải khoảng cách kênh)."""
    p = np.asarray(power, dtype=float)
    if p.ndim == 1:
        p = p[None, :]
    mu, sd = p.mean(axis=0), p.std(axis=0)
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = np.where(mu > 0, sd / np.where(mu > 0, mu, 1), np.nan)
    theory = 1.0 / math.sqrt(max(df_hz * dt_s, 1e-15))
    med = float(np.nanmedian(ratio))
    dev = (med - theory) / theory
    return dict(theory=round(theory, 5), measured=round(med, 5),
                deviation=round(float(dev), 3),
                tag="GAIN_DRIFT" if dev > RADIOMETER_TOL else "OK")


def spectral_kurtosis(power) -> dict:
    """SK (Nita) từng kênh; M ≥ ~1000 mẫu/kênh mới đáng tin."""
    p = np.asarray(power, dtype=float)
    if p.ndim == 1:
        p = p[:, None]
    M = p.shape[0]
    if M < 50:
        return dict(sk=None, bad_channels=[], n_bad=0, sigma=None,
                    note=f"quá ít mẫu (M={M})")
    s1 = p.sum(axis=0)
    s2 = (p ** 2).sum(axis=0)
    with np.errstate(divide="ignore", invalid="ignore"):
        sk = (M + 1) / (M - 1) * (M * s2 / (s1 ** 2) - 1)
    sk = np.nan_to_num(sk, nan=1.0)
    sigma = math.sqrt(4.0 / M)
    # Dữ liệu thật (tổng công suất đã tích phân, gain trôi, RFI nền) làm SK lệch
    # khỏi 1 một cách HỆ THỐNG → so với 1 sẽ đánh dấu gần như mọi kênh (đã gặp:
    # 99,6 %). Vì vậy dò **kênh dị biệt** so với trung vị của chính file:
    #   thr = max(5·MAD(SK), 0,2)  → bắt kênh bất thường, không bắt cả nền.
    med = float(np.median(sk))
    mad = 1.4826 * float(np.median(np.abs(sk - med))) + 1e-9
    thr = max(5.0 * mad, 0.2)
    bad = np.where(np.abs(sk - med) > thr)[0]
    return dict(sigma=round(sigma, 5), sk_median=round(med, 3),
                sk_mad=round(mad, 3), threshold=round(thr, 3),
                bad_channels=bad.tolist()[:50], n_bad=int(bad.size), note="")


def thermal_check(meta: dict, tsys_nominal_k: float | None = None) -> dict:
    """T_sys và trôi nhiệt LNA → có rút ngắn cửa sổ bandpass không."""
    t = meta.get("telemetry") or {}
    out = dict(tag="OK", bandpass_window_s=600, warnings=[])
    tsys = t.get("tsys_k")
    if tsys is not None and tsys_nominal_k and tsys > TSYS_FACTOR * tsys_nominal_k:
        out.update(tag="DEGRADED")
        out["warnings"].append(
            f"T_sys {tsys:.0f} K > 1,5× chuẩn ({tsys_nominal_k:.0f} K) — kiểm tra "
            f"góc Mặt Trời và elevation < 15°")
    d = t.get("dt_lna_c")
    if d is not None and abs(d) > DT_LNA_LIMIT:
        out.update(bandpass_window_s=180)
        out["warnings"].append(
            f"ΔT_LNA = {d:+.1f} °C → rút cửa sổ bandpass 600→180 s "
            f"(nhiễu ước lượng tăng √(600/180) ≈ 1,8×)")
    return out


# ============================================================ máy trạng thái
def inspect(path: str, meta: dict | None = None, sample_rows: int = 2000) -> dict:
    """Inspect → Sanitize → Gatekeep → Tagging cho MỘT file/hiện trường."""
    rep = dict(path=os.path.basename(path), steps={}, actions=[], warnings=[],
               metrics={}, tags=[], stage=None, inferred=[], ok=True,
               schema_version=3)
    a = validate_metadata(meta)
    rep["metadata"] = dict(missing=a["missing"], problems=a["problems"],
                           complete=a["complete"])
    if a["missing"]:
        rep["inferred"] = list(a["missing"])
        rep["warnings"].append("thiếu metadata: " + ", ".join(a["missing"])
                               + " → suy ra từ nội dung")

    fmt = sniff_format(path)
    rep["steps"]["format"] = fmt
    rep["input_sha256"] = input_fingerprint(path).get("sha256_head")
    hint = (meta or {}).get("stage") or fmt.get("stage")
    tsamp = (meta or {}).get("tsamp_s")
    sample = None

    if fmt["kind"] == "text":
        tab = read_table_text(path)
        rep["steps"]["table"] = {k: tab[k] for k in
                                 ("kind", "ncol", "nrow", "header_lines",
                                  "delimiter", "truncated")}
        if tab["rows"] is not None:
            sample, srep = sanitize_nonfinite(tab["rows"], "table")
            rep["steps"]["sanitize"] = srep
            if srep["tag"] == "CORRUPTED":
                rep["tags"].append("CORRUPTED")
            elif srep["tag"] == "REPAIRED":
                rep["warnings"].append(srep["note"])
            if tab["kind"] == "spectrum_1d":
                rep["tags"].append("SPECTRUM_1D")
                rep["warnings"].append(
                    "phổ 1D (chỉ có công suất) → đủ cho HI/continuum, KHÔNG đủ "
                    "trục thời gian để tìm pulsar")
            else:
                rep["tags"].append("MATRIX_2D")
                if tab["nrow"] >= 2:
                    dt = float(np.median(np.diff(tab["rows"][:, 0])))
                    tsamp = dt if dt < 10 else dt / 1000.0
                    rep["metrics"]["tsamp_from_table"] = tsamp
        rep["warnings"].extend(tab["problems"])
    elif fmt["kind"] in ("sigproc", "psrfits"):
        try:
            if fmt["kind"] == "sigproc":
                from psr_fil import read_fil
                h1, d1 = read_fil(path, max_seconds=1.0)
            else:
                from psr_fits import read_psrfits
                h1, d1 = read_psrfits(path, max_seconds=1.0)
            tsamp = h1.get("tsamp_s")
            sample = d1[:, :sample_rows]
            rep["metrics"]["nchan_from_header"] = int(h1.get("nchans", 0))
            rep["warnings"].extend(h1.get("read_warnings") or [])
        except Exception as exc:                 # noqa: BLE001
            rep["warnings"].append(f"không đọc được {fmt['kind']}: {exc!r}")
    else:
        sl = read_sample_slices(path, fmt)
        rep["steps"]["slices"] = {k: int(len(sl[k])) for k in SNIFF_SLICES}
        rep["steps"]["raw_dtype"] = sl["dtype"]
        parts = [sl[k] for k in SNIFF_SLICES if len(sl[k])]
        sample = np.concatenate(parts) if parts else None
        if fmt["kind"] == "binary":
            rep["warnings"].append("container không xác định — đoán dtype; nên "
                                   "cung cấp metadata")

    if sample is None or np.asarray(sample).size == 0:
        rep.update(ok=False, stage="UNKNOWN")
        rep["warnings"].append("không đọc được mẫu nào")
        rep["tags"].append("UNREADABLE")
        return rep

    fp = fingerprint(sample, tsamp_s=tsamp, meta=dict(meta or {}, stage=hint))
    rep["stage"] = hint or fp["stage"]
    rep["actions"] = fp["actions"]
    rep["metrics"].update(fp["metrics"])
    rep["warnings"].extend(fp["warnings"])
    rep["steps"]["fingerprint"] = fp["metrics"]

    key, _, bits = _dtype_of(fmt.get("datatype"))
    bits = int((meta or {}).get("adc_bits") or bits or 8)
    rep["metrics"]["adc_bits"] = bits
    gate = {"thermal": thermal_check(meta or {}, (meta or {}).get("tsys_nominal_k"))}
    if rep["stage"] == "RAW_IQ":
        gate["adc"] = adc_clipping(sample, bits)
    else:
        gate["adc"] = dict(frac=0.0, max_run=0, tag="N/A", limit=bits,
                           note="dữ liệu đã qua FFT — không đo bão hoà ADC ở đây")
    p = np.asarray(sample, dtype=float) if not np.iscomplexobj(sample) else None
    if p is not None and p.ndim == 2 and p.shape[0] > 8:
        freqs = (meta or {}).get("freqs_mhz")
        if freqs is not None and len(freqs) > 1 and tsamp:
            bw = abs(float(np.max(freqs) - np.min(freqs))) * 1e6
            gate["radiometer"] = radiometer_check(p, bw / len(freqs), tsamp)
        gate["sk"] = spectral_kurtosis(p.T)   # (ntime, nchan)
    rep["steps"]["gatekeeper"] = gate

    tags = set(rep["tags"])
    if gate["adc"]["tag"] == "ABORT":
        tags.add("SATURATED")
    elif gate["adc"]["tag"] == "WARN":
        tags.add("ADC_WARN")
    if gate.get("radiometer", {}).get("tag") == "GAIN_DRIFT":
        tags.add("GAIN_DRIFT")
    _sk = gate.get("sk") or {}
    _sarr = np.asarray(sample)
    if _sk.get("n_bad", 0) and _sarr.ndim == 2 and _sarr.shape[0]:
        _frac = _sk["n_bad"] / max(1, _sarr.shape[0])
        if 0.05 < _frac <= 0.5:
            tags.add("RFI_HEAVY")      # một phần kênh → RFI hẹp băng
        elif _frac > 0.5:
            tags.add("GAIN_DRIFT")     # gần như mọi kênh → nền không dừng
    if gate["thermal"]["tag"] == "DEGRADED":
        tags.add("DEGRADED")
    rep["tags"] = sorted(tags or {"VALID"})
    rep["ok"] = not (tags & {"UNREADABLE", "SATURATED", "CORRUPTED"})
    return rep


def analyze_array(dyn, header: dict, meta: dict | None = None,
                  max_cols: int = 4000) -> dict:
    """Lớp B + gatekeeper trên mảng ĐÃ ĐỌC (pipeline đã biết chắc định dạng)."""
    x = np.asarray(dyn)
    meta = dict(meta or {})
    ts = meta.get("tsamp_s") or header.get("tsamp_s")
    rep = dict(path=os.path.basename(str(meta.get("path", header.get("source", "")))),
               steps={}, actions=[], warnings=[], metrics={}, tags=[],
               stage=meta.get("stage"), inferred=[], ok=True, schema_version=3)
    _p = meta.get("path")
    if _p and os.path.exists(str(_p)):
        try:
            rep["steps"]["format"] = sniff_format(str(_p))
        except Exception:                        # noqa: BLE001
            pass
    sample = x[:, :max_cols] if x.ndim == 2 else x[:max_cols]
    xc, srep = sanitize_nonfinite(sample, "dyn")
    if srep["tag"] == "REPAIRED":
        rep["warnings"].append(srep["note"])
    rep["steps"]["sanitize"] = srep
    fp = fingerprint(xc, tsamp_s=ts, meta=meta)
    rep.update(stage=meta.get("stage") or fp["stage"], actions=fp["actions"],
               metrics=dict(fp["metrics"]), warnings=rep["warnings"] + fp["warnings"])

    gate = {"thermal": thermal_check(meta, meta.get("tsys_nominal_k"))}
    if rep["stage"] == "RAW_IQ":
        gate["adc"] = adc_clipping(sample, int(meta.get("adc_bits", 8)))
    if x.ndim == 2 and x.shape[0] > 8:
        gate["sk"] = spectral_kurtosis(xc.T)   # (ntime, nchan)
        freqs = header.get("freqs_mhz")
        if freqs is not None and len(freqs) > 1 and ts:
            bw = abs(float(np.max(freqs) - np.min(freqs))) * 1e6
            gate["radiometer"] = radiometer_check(xc, bw / len(freqs), ts)
    rep["steps"]["gatekeeper"] = gate

    tags = set()
    if srep["tag"] == "CORRUPTED":
        tags.add("CORRUPTED")
    if gate.get("adc", {}).get("tag") == "ABORT":
        tags.add("SATURATED")
    if gate.get("radiometer", {}).get("tag") == "GAIN_DRIFT":
        tags.add("GAIN_DRIFT")
    _sk = gate.get("sk") or {}
    _sarr = np.asarray(sample)
    if _sk.get("n_bad", 0) and _sarr.ndim == 2 and _sarr.shape[0]:
        _frac = _sk["n_bad"] / max(1, _sarr.shape[0])
        if 0.05 < _frac <= 0.5:
            tags.add("RFI_HEAVY")      # một phần kênh → RFI hẹp băng
        elif _frac > 0.5:
            tags.add("GAIN_DRIFT")     # gần như mọi kênh → nền không dừng
    if gate["thermal"]["tag"] == "DEGRADED":
        tags.add("DEGRADED")
    rep["tags"] = sorted(tags or {"VALID"})
    rep["ok"] = not (tags & {"SATURATED", "CORRUPTED", "UNREADABLE"})
    return rep


def summary(rep: dict) -> str:
    return (f"stage={rep.get('stage')} tags={','.join(rep.get('tags') or [])} "
            f"actions={','.join(rep.get('actions') or []) or '-'}"
            + (f" | {rep['warnings'][0]}" if rep.get("warnings") else ""))


# ============================================================ tự kiểm
def self_check() -> list:
    bad = []
    rng = np.random.default_rng(3)

    iq = (rng.normal(size=4096) + 1j * rng.normal(size=4096)).astype(np.complex64)
    fp = fingerprint(iq)
    if fp["stage"] != "RAW_IQ" or "fft" not in fp["actions"]:
        bad.append(f"IQ: {fp['stage']} {fp['actions']}")

    pw = np.abs(rng.normal(size=(200, 256))) ** 2 + 1.0
    fp = fingerprint(pw, tsamp_s=1e-3)
    if fp["stage"] != "CHANNELIZED_POWER" or "flatten" in fp["actions"]:
        bad.append(f"power phẳng: {fp['stage']} {fp['actions']}")
    if "route:pulsar" not in fingerprint(pw, tsamp_s=2e-4)["actions"]:
        bad.append("Δt 0,2 ms không route pulsar")
    if "route:hi_continuum" not in fingerprint(pw, tsamp_s=1.0)["actions"]:
        bad.append("Δt 1 s không route HI")

    n = 256
    x = np.linspace(-1, 1, n)
    pw2 = np.tile(1.0 + 2.0 * (1 - x ** 2), (100, 1)) * (1 + 0.01 * rng.normal(size=(100, n)))
    fp = fingerprint(pw2, tsamp_s=1e-3)
    if not {"flatten", "edge_zap"} <= set(fp["actions"]):
        bad.append(f"bandpass vòm: {fp['actions']}")
    pw3 = pw2.copy()
    pw3[:, n // 2] *= 50
    if "dc_notch" not in fingerprint(pw3, tsamp_s=1e-3)["actions"]:
        bad.append("DC spike không phát hiện")

    if adc_clipping(np.full(8192, 127, dtype=np.int8), 8)["tag"] != "ABORT":
        bad.append("bão hoà toàn bộ không ABORT")
    if adc_clipping(rng.normal(size=8192) * 10, 8)["tag"] != "OK":
        bad.append("mẫu sạch báo bão hoà")

    base = np.abs(rng.normal(size=(2000, 32))) ** 2 + 1.0
    base[:, 5] = 100.0 + 1e-3 * rng.normal(size=2000)
    if 5 not in spectral_kurtosis(base)["bad_channels"]:
        bad.append("SK không bắt kênh CW")

    # Q3: NaN
    a2 = np.ones((100, 4))
    a2[10, 1] = np.nan
    _, srep = sanitize_nonfinite(a2)
    if srep["tag"] != "REPAIRED" or srep["replaced"] != 1:
        bad.append(f"NaN 0,25 % chưa sửa: {srep}")
    a3 = np.ones((100, 4))
    a3[::3, :] = np.nan
    if sanitize_nonfinite(a3)[1]["tag"] != "CORRUPTED":
        bad.append("NaN 33 % không bị CORRUPTED")

    # Q1/Q2/Q4: chạy được
    import tempfile
    tmp = tempfile.mkdtemp(prefix="igsc_")
    try:
        p1 = os.path.join(tmp, "spec.csv")
        with open(p1, "w", encoding="utf-8") as fh:
            fh.write("# RTCS v2 export\n# freq_MHz,power\nfreq,power\n")
            for i in range(64):
                fh.write(f"{1400+i*0.1:.3f},{10+i*0.01:.3f}\n")
        t1 = read_table_text(p1)
        if t1["kind"] != "spectrum_1d" or t1["ncol"] != 2 or t1["header_lines"] < 3:
            bad.append(f"CSV 1D: {t1['kind']} ncol={t1['ncol']} hdr={t1['header_lines']}")

        p2 = os.path.join(tmp, "dyn.csv")
        with open(p2, "w", encoding="utf-8") as fh:
            fh.write("time_s," + ",".join(f"ch{i}" for i in range(8)) + "\n")
            for i in range(50):
                fh.write(f"{i*0.001:.6f}," + ",".join("1.0" for _ in range(8)) + "\n")
        t2 = read_table_text(p2)
        if t2["kind"] != "matrix_2d" or t2["ncol"] != 9:
            bad.append(f"CSV 2D: {t2['kind']} ncol={t2['ncol']}")

        # dấu phẩy thập phân
        p3 = os.path.join(tmp, "euro.csv")
        with open(p3, "w", encoding="utf-8") as fh:
            fh.write("t;ch0;ch1\n")
            for i in range(30):
                fh.write(f"{i*0.001:.3f};{1+i*0.01:.2f};2.0\n".replace(".", ","))
        t3 = read_table_text(p3)
        if t3["kind"] != "matrix_2d" or not np.allclose(t3["rows"][0], [0, 1, 2]):
            bad.append(f"CSV dấu phẩy: {t3['kind']} {None if t3['rows'] is None else t3['rows'][0]}")

        # container: file giả SIGPROC
        p4 = os.path.join(tmp, "fake.fil")
        with open(p4, "wb") as fh:
            fh.write(b"HEADER_START" + bytes(100) + b"data")
        if sniff_format(p4)["kind"] != "sigproc":
            bad.append("sniff_format không nhận SIGPROC")

        # Q1: đọc lát cắt không nạp cả file
        p5 = os.path.join(tmp, "big.bin")
        with open(p5, "wb") as fh:
            fh.write(bytes(4_000_000))
        sl = read_sample_slices(p5, dict(datatype="ci8"))
        if sl["head"].size > 2_000_001 or sl["size"] != 4_000_000:
            bad.append(f"slices sai: {sl['head'].size}/{sl['size']}")
        if max(len(sl[k]) for k in SNIFF_SLICES) > 2_000_001:
            bad.append("lát cắt vượt 2 MB")

        # Q2: preflight + ghi nguyên tử
        if not disk_preflight(tmp, 1e6)["ok"]:
            bad.append("preflight báo fail sai")
        pj = os.path.join(tmp, "x.json")
        atomic_write_json(pj, {"a": 1})
        if not os.path.exists(pj) or os.path.exists(pj + ".tmp"):
            bad.append("atomic_write_json sai")
        # Q4: chặn ghi vào dữ liệu thô
        try:
            refuse_write_into_raw(os.path.join(tmp, "d", "x.json"), os.path.join(tmp, "d"))
            bad.append("refuse_write_into_raw không chặn")
        except PermissionError:
            pass
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return bad


if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                            # noqa: BLE001
        pass
    errs = self_check()
    print("ingest_guard self_check:", "PASS" if not errs else errs)
    sys.exit(0 if not errs else 1)
