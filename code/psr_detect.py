# -*- coding: utf-8 -*-
"""
psr_detect.py — Pipeline phát hiện pulsar trên DỮ LIỆU THẬT (filterbank .fil),
có kiểm chứng số liệu ĐẦU VÀO và ĐẦU RA.

    python psr_detect.py                          # chạy trên data/B0329+54.fil
    python psr_detect.py --file <đường_dẫn.fil> [--dm-ref 26.764] [--p 0.714519]

Luồng xử lý:
    V1  đọc .fil + kiểm chứng đầu vào (số mẫu, NaN, kênh nóng, RFI xung)
    A1  flag kênh + chuẩn hoá bandpass
    A9  khử RFI zero-DM (cảnh báo: không được cắt nhầm xung tán sắc)
    A8  quét DM cho XUNG ĐƠN (lọc khớp boxcar đa độ rộng)
    A7  gom cụm ứng viên → danh sách xung thật
    A11c đo DM từng xung bằng trễ giữa các dải con
    V2  kiểm chứng đầu ra: DM vs tham chiếu, số xung, SNR đối chứng nền
    A4  fold theo P catalogue (nếu đủ ≥ 5 chu kỳ)

Sản phẩm (results/):
    real_detect_metrics.json   mọi số đo + trạng thái kiểm chứng
    real_detect_report.txt     báo cáo dễ đọc
    real_fig1_overview.png     waterfall thô + đã khử tán sắc
    real_fig2_detection.png    chuỗi thời gian + quét DM + hồ sơ xung + trễ dải con
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from psr_core import (K_DM, boxcar_snr, dedisperse, ensure_utf8_stdout,
                      find_pulses, fold, profile_snr, subband_dm_single,
                      zero_dm_excise, mask_bad_channels, bandpass_normalize)
from psr_fil import read_fil
from psr_fits import read_psrfits


# đuôi file IQ THÔ (chưa channelize) — phải channelize trước khi phân tích
IQ_EXTS = (".sigmf-data", ".cu8", ".cs8", ".ci8", ".cu16", ".cs16", ".ci16",
           ".cf32", ".fc32", ".iq", ".wav", ".npy")


def load_any(path: str, max_seconds: float | None = None, nchan_iq: int = 256,
             navg_iq: int = 16):
    """Đọc file bất kỳ: SIGPROC .fil | PSRFITS .fits | **IQ thô** (SigMF/.cu8/.wav…).

    Với IQ thô, bước A1 (channelize) được thực hiện ngay tại đây — đúng đường
    đi thật của tín hiệu: dây → SDR → I/Q → FFT → kênh → tìm pulsar.
    """
    low = path.lower()
    # ---- NHẬN DẠNG THEO NỘI DUNG trước, đuôi file chỉ là gợi ý.
    # (đã gặp: file .ar của MeerKAT/TRAPUM thực chất là PSRFITS, đổi đuôi;
    #  nếu chỉ dựa vào đuôi thì bị đọc sai và báo unreadable)
    try:
        kind = guard.sniff_format(path).get("kind")
    except Exception:
        kind = None
    if kind == "psrfits":
        return read_psrfits(path, max_seconds=max_seconds)
    if kind == "sigproc":
        return read_fil(path, max_seconds=max_seconds)
    if kind == "text":
        return read_table_as_dyn(path, max_seconds=max_seconds)
    if kind in ("sigmf", "wav"):
        from psr_iq import read_iq_as_dyn
        return read_iq_as_dyn(path, nchan=nchan_iq, navg=navg_iq,
                              max_seconds=max_seconds)

    # ---- không nhận ra bằng nội dung → dùng đuôi file
    if low.endswith((".fits", ".psrfits", ".sf", ".rf", ".cf")):
        return read_psrfits(path, max_seconds=max_seconds)
    if low.endswith(IQ_EXTS):
        from psr_iq import read_iq_as_dyn
        return read_iq_as_dyn(path, nchan=nchan_iq, navg=navg_iq,
                              max_seconds=max_seconds)
    if low.endswith((".csv", ".tsv", ".txt")):
        return read_table_as_dyn(path, max_seconds=max_seconds)
    # đuôi lạ: thử SIGPROC, rồi bảng text
    try:
        return read_fil(path, max_seconds=max_seconds)
    except Exception as exc_fil:
        try:
            return read_table_as_dyn(path, max_seconds=max_seconds)
        except Exception:
            raise exc_fil


def read_table_as_dyn(path: str, max_seconds: float | None = None):
    """Đọc CSV/TSV phổ do back-end xuất (RTCS/N6002) → (header, dyn).

    Chỉ dùng được với **ma trận 2D (time × freq)**. Phổ 1D bị từ chối kèm lời
    khuyên, vì không có trục thời gian thì không thể fold/tìm pulsar.
    """
    tab = guard.read_table_text(path)
    if tab["rows"] is None or tab["kind"] == "unknown":
        raise ValueError("không phải bảng số đọc được: "
                         + "; ".join(tab["problems"]))
    if tab["kind"] == "spectrum_1d":
        raise ValueError(
            "đây là phổ 1D (chỉ có trục tần số): đủ cho HI/continuum nhưng "
            "KHÔNG đủ trục thời gian để tìm pulsar. Cần xuất ma trận "
            "time × frequency (mỗi dòng là một mốc thời gian).")
    arr = tab["rows"]
    tcol = arr[:, 0] if tab.get("time_axis") is not None else None
    data = arr[:, 1:] if tcol is not None else arr
    if max_seconds and tcol is not None:
        keep = tcol <= tcol[0] + max_seconds
        data, tcol = data[keep], tcol[keep]
    tsamp = float(np.median(np.diff(tcol))) if tcol is not None and tcol.size > 1 else None
    if tsamp is not None and tsamp > 10:      # đơn vị ms
        tsamp /= 1000.0
    tsamp = tsamp or 1e-3
    nch = data.shape[1]
    # trục tần số: nếu file có cột tần số thì dùng, ngược lại giả định 1400 MHz
    freqs = np.linspace(1400.0, 1400.0, nch)
    h = dict(source=os.path.basename(path), nbits=32, nchans=nch,
             tsamp=tsamp, tsamp_s=tsamp, ntime=data.shape[0],
             t_s=data.shape[0] * tsamp, freqs_mhz=freqs,
             tstart=None, data_file_bytes=os.path.getsize(path),
             read_warnings=[f"đọc từ bảng text: {tab['ncol']} cột, "
                            f"{tab['header_lines']} dòng header bị bỏ qua"])
    h["validation"] = dict(ok=True, problems=[], warnings=h["read_warnings"],
                           stats=dict(mean=float(np.mean(data)),
                                      std=float(np.std(data)),
                                      nchan=nch, ntime=int(data.shape[0])))
    # bảng là (time × freq) — pipeline cần (chan × time)
    return h, np.ascontiguousarray(data.astype(np.float32).T)
import psr_plots as pp
import ingest_guard as guard
import psr_period as per
import psr_paths as paths

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = paths.results_dir()       # chính sách I/O tập trung (psr_paths)
DATA = paths.data_dir()

# Mốc tham chiếu lấy từ DANH MỤC (psr_targets.PULSARS) — chỉ để KIỂM CHỨNG,
# không dùng để "tìm". Không có mốc thì KHÔNG vẽ đường tham chiếu (tránh gán
# DM của pulsar khác lên dữ liệu, như từng xảy ra: Cua bị so với 26.76).
_ALIAS = {"crab": "B0531+21", "cua": "B0531+21", "vela": "B0833-45"}


def ref_from_catalogue(path: str = "", source: str = "") -> dict | None:
    """Tra DM/P của mục tiêu từ tên file hoặc tên nguồn trong header.

    Trả None nếu không nhận ra — KHÔNG đoán bừa.
    """
    import re
    try:
        from psr_targets import PULSARS
    except Exception:
        PULSARS = []
    blob = f"{path} {source}".upper()
    # So khớp theo PHẦN GỐC của tên (B0531, J0437, B0329...): người dùng hay
    # đặt tên file kiểu "injected_B0531.fil" hoặc "B0329+54.fil".
    for t in PULSARS:
        core = t["name"].upper().split("+")[0].split("-")[0]
        if re.search(rf"(?<![A-Z0-9]){re.escape(core)}(?![0-9])", blob):
            return dict(dm=t["dm"], p_s=t["P"], w50_ms=t.get("w408"),
                        name=t["name"], from_="tên file/nguồn")
    low = blob.lower()
    for word, name in _ALIAS.items():
        if word in low:
            for t in PULSARS:
                if t["name"] == name:
                    return dict(dm=t["dm"], p_s=t["P"], w50_ms=t.get("w408"),
                                name=t["name"], from_=f'từ khoá "{word}"')
    return None


MAX_STEM = 60          # giới hạn tên thư mục kết quả (an toàn MAX_PATH Windows)


def safe_stem(name: str) -> str:
    """Tên thư mục kết quả AN TOÀN: bỏ ký tự cấm, cắt ngắn, giữ duy nhất.

    Vì sao cần: tên file dữ liệu có thể rất dài hoặc chứa ký tự Windows không
    cho phép; ghép thẳng vào đường dẫn results/ có thể vượt giới hạn đường dẫn
    hoặc gây OSError khó hiểu khi ghi ảnh.
    """
    import hashlib
    raw = str(name or "").strip()
    bad = '<>:"/' + chr(92) + '|?*'
    s = "".join("_" if c in bad else c for c in raw).strip(" .")
    if not s:
        s = time.strftime("%Y%m%d")
    if len(s) > MAX_STEM:
        h = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:8]
        s = s[: MAX_STEM - 9].rstrip() + "~" + h
    return s


def _savefig(fig, path: str, tries: int = 4) -> None:
    """savefig có thử lại: Windows/AV có thể khoá file trong tích tắc."""
    for k in range(tries):
        try:
            fig.savefig(path)
            return
        except OSError as e:
            if k == tries - 1:
                raise OSError(
                    f"không ghi được {path} sau {tries} lần: {e}. "
                    f"Kiểm tra dung lượng ổ đĩa / quyền ghi / phần mềm diệt virus."
                ) from e
            time.sleep(0.4 * (k + 1))


def _jsonify(o):
    """Chuyển numpy bool/int/float → kiểu Python chuẩn để json.dump không lỗi."""
    if isinstance(o, dict):
        return {k: _jsonify(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_jsonify(v) for v in o]
    if isinstance(o, np.bool_):
        return bool(o)
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.floating):
        return float(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    return o



def _write_min_report(out_dir: str, path: str, h: dict, m: dict):
    """Báo cáo tối thiểu khi dữ liệu không dùng được (rỗng/quá ngắn/phẳng)."""
    lines = [f"BÁO CÁO (không phân tích) — {os.path.basename(path)}",
             f"trạng thái: {m.get('status')}",
             f"{h.get('nchans')} kênh × {h.get('ntime')} mẫu, "
             f"{h.get('t_s'):.2f} s, {h.get('nbits')} bit",
             "vấn đề: " + ("; ".join(m.get("problems", [])) or "dữ liệu quá ngắn")]
    txt = "\n".join(lines)
    with open(os.path.join(out_dir, "detect_report.txt"), "w",
              encoding="utf-8") as fh:
        fh.write(txt + "\n")
    guard.atomic_write_json(os.path.join(out_dir, "detect_metrics.json"),
                            _jsonify(m))       # Q2: ghi nguyên tử
    print(txt)


def rebin_channels(dyn, rb: int, block: int = 512) -> np.ndarray:
    """Gộp `rb` kênh liền nhau, theo KHỐI để RAM không phụ thuộc số kênh."""
    d = np.asarray(dyn)
    if rb <= 1:
        return d.astype(np.float32, copy=False)
    nch, nt = d.shape
    nnew = nch // rb
    out = np.empty((nnew, nt), dtype=np.float32)
    for i in range(0, nnew, block):
        j = min(i + block, nnew)
        sl = d[i * rb: j * rb]
        out[i:j] = sl.reshape(j - i, rb, nt).sum(axis=1, dtype=np.float32) / rb
    return out


def detect(path: str, dm_ref: float | None = None, p_ref: float | None = None,
           dm_max: float | None = None, dm_step: float = 0.25,
           pulse_thresh: float = 8.0, rebin: int = 8,
           nchan_iq: int = 256, navg_iq: int = 16,
           out_name: str | None = None, search_period: bool = False,
           pmin_s: float = 0.0015, pmax_s: float = 10.0,
           top_n: int = 10) -> dict:
    os.makedirs(RESULTS, exist_ok=True)
    # GOM sản phẩm của MỘT lần chạy vào MỘT thư mục: tên theo file dữ liệu
    # (data/<tên>.fil → results/<tên>/), mặc định theo ngày nếu không có tên.
    # TÊN THƯ MỤC KẾT QUẢ = NGÀY + GIỜ lưu (mỗi lần chạy là một bản ghi riêng,
    # không ghi đè kết quả cũ). Vẫn có thể ép tên qua out_name (dùng cho test).
    base = out_name or time.strftime("%Y%m%d_%H%M%S")
    stem = safe_stem(base)
    out_dir = os.path.join(RESULTS, stem)
    k = 2
    while os.path.exists(os.path.join(out_dir, "detect_metrics.json")):
        out_dir = os.path.join(RESULTS, f"{stem}_{k}")
        k += 1
    paths.assert_write_allowed(out_dir)             # Q4: data/ là chỉ đọc
    m: dict = {"file": os.path.basename(path), "out_dir": out_dir, "stage": {},
               "schema_version": 3,
               "input_sha256": guard.input_fingerprint(path).get("sha256_head")}
    # kiểm tra ghi được TRƯỚC khi làm bất cứ việc gì (thư mục chỉ-đọc, hết đĩa…)
    try:
        os.makedirs(out_dir, exist_ok=True)
        _probe = os.path.join(out_dir, ".write_probe")
        with open(_probe, "w", encoding="utf-8") as _fh:
            _fh.write("ok")
        os.remove(_probe)
    except OSError as _exc:
        m["status"] = "write_error"
        m["problems"] = [f"không ghi được vào {out_dir}: {_exc}"]
        print(f"→ DỪNG: không ghi được kết quả vào {out_dir} ({_exc}). "
              f"Kiểm tra quyền ghi / dung lượng ổ đĩa.")
        return m

    if dm_ref is None or p_ref is None:
        # chỉ dùng mốc khi NHẬN RA mục tiêu từ tên file / header
        _r = ref_from_catalogue(path, "")
        if _r:
            dm_ref = dm_ref if dm_ref is not None else _r["dm"]
            p_ref = p_ref if p_ref is not None else _r["p_s"]
            m["reference"] = _r

    # ---------------- V1: đọc + kiểm chứng đầu vào (tự nhận .fil/.fits)
    try:
        h, dyn = load_any(path, nchan_iq=nchan_iq, navg_iq=navg_iq)
    except Exception as e:
        # file hỏng/rỗng/sai định dạng: KHÔNG crash — ghi chẩn đoán rồi dừng
        m["status"] = "unreadable"
        m["problems"] = [f"{type(e).__name__}: {e}"]
        print(f"→ KHÔNG ĐỌC ĐƯỢC {os.path.basename(path)}: {e}")
        with open(os.path.join(out_dir, "detect_report.txt"), "w",
                  encoding="utf-8") as fh:
            fh.write(f"BÁO CÁO CHẨN ĐOÁN — {os.path.basename(path)}\n"
                     f"trạng thái: unreadable\n"
                     f"lỗi: {type(e).__name__}: {e}\n")
        with open(os.path.join(out_dir, "detect_metrics.json"), "w",
                  encoding="utf-8") as fh:
            json.dump(_jsonify(m), fh, ensure_ascii=False, indent=2)
        return m
    freqs = h["freqs_mhz"]
    tsamp = h["tsamp_s"]
    m["input"] = {k: h.get(k) for k in ("source", "nbits", "nchans", "tsamp_s",
                                        "tstart", "t_s", "ntime")}
    m["input"]["band_mhz"] = [float(freqs.min()), float(freqs.max())]
    m["input"]["validation"] = h["validation"]
    # mốc tham chiếu: ưu tiên người dùng nhập; nếu không, tra theo header
    # (tên nguồn) rồi tới tên file. Không nhận ra → KHÔNG có mốc nào.
    if dm_ref is None or p_ref is None:
        _r2 = ref_from_catalogue(path, h.get("source") or "")
        if _r2:
            dm_ref = dm_ref if dm_ref is not None else _r2["dm"]
            p_ref = p_ref if p_ref is not None else _r2.get("p_s")
            m["reference"] = _r2
            print(f"→ mốc tham chiếu: {_r2['name']} DM = {_r2['dm']} "
                  f"({_r2['from_']}) — CHỈ dùng để kiểm chứng")
    print(f"→ V1 đọc {path}: {h['nchans']} kênh, {h['ntime']} mẫu, "
          f"{h['t_s']:.2f} s, {freqs.min():.0f}–{freqs.max():.0f} MHz")
    for w in h.get("read_warnings", []) or h["validation"]["warnings"]:
        print(f"   ⚠ {w}")

    # ---- GUARD: nhận dạng trạng thái + gatekeeper (docs/07 §6c)
    _stage = ("RAW_IQ" if os.path.basename(path).lower().endswith(IQ_EXTS)
              else "CHANNELIZED_POWER")
    try:
        m["guard"] = guard.analyze_array(
            dyn, h, meta=dict(path=path, stage=_stage, tsamp_s=tsamp,
                              adc_bits=h.get("nbits", 8), gaps=[]))
        print(f"→ guard: {guard.summary(m['guard'])}")
        for _w in m["guard"].get("warnings", [])[:3]:
            print(f"   ⚠ {_w}")
        if not m["guard"].get("ok", True):
            m["status"] = "invalid"
            m["problems"] = (m.get("problems") or []) + [
                "guard: " + t for t in m["guard"].get("tags", [])]
            print("→ DỪNG: guard đánh giá dữ liệu không dùng được")
            _write_min_report(out_dir, path, h, m)
            return m
    except Exception as _e:
        m["guard"] = dict(ok=None, error=repr(_e))
        print(f"   ⚠ guard lỗi: {_e!r}")

    # ---- CHẶN SỚM: dữ liệu không dùng được thì báo rõ, KHÔNG crash
    m["status"] = "ok"
    if not h["validation"]["ok"]:
        m["status"] = "invalid"
        m["problems"] = h["validation"]["problems"]
        print(f"→ DỪNG: dữ liệu không hợp lệ: {h['validation']['problems']}")
        _write_min_report(out_dir, path, h, m)
        return m
    # Guard theo THỜI LƯỢNG (không chỉ số mẫu): 0.2 s vẫn đủ bắt giant pulse
    # (dữ liệu Dwingeloo), nhưng 4 ms (200 mẫu) thì vô nghĩa.
    if int(h.get("nchans", 0) or 0) < 4:
        m["status"] = "invalid"
        m["problems"] = [f"chỉ có {h.get('nchans')} kênh — không thể khử tán sắc "
                         f"hay đo DM; cần dữ liệu đa kênh (PSRFITS/filterbank)"]
        print(f"→ DỪNG: {m['problems'][0]}")
        _write_min_report(out_dir, path, h, m)
        return m
    if h["ntime"] < 100 or h["t_s"] < 0.05:
        m["status"] = "too_short"
        print(f"→ DỪNG: quá ngắn ({h['ntime']} mẫu, {h['t_s']:.4f} s) — "
              f"cần ≥ 100 mẫu VÀ ≥ 0.05 s (0.2 s vẫn đủ bắt giant pulse)")
        _write_min_report(out_dir, path, h, m)
        return m

    # ---------------- A1: flag kênh + bandpass
    good = mask_bad_channels(dyn.astype(np.float64), sigma=5.0)
    dyn_n = bandpass_normalize(dyn[good].astype(np.float64))
    f_g = freqs[good]
    m["stage"]["channels_kept"] = int(good.sum())
    m["stage"]["channels_flagged"] = int((~good).sum())
    print(f"→ A1 giữ {good.sum()}/{len(good)} kênh")

    # ---------------- A9: zero-DM RFI
    dyn_z, bad_t = zero_dm_excise(dyn_n, threshold=6.0)
    m["stage"]["zero_dm_cut_samples"] = int(bad_t.sum())
    m["stage"]["zero_dm_cut_frac"] = float(bad_t.mean())
    print(f"→ A9 zero-DM: cắt {bad_t.sum()} mẫu ({100*bad_t.mean():.1f}%)")

    # ---------------- gộp kênh để quét DM nhanh (trải nội kênh phải < tsamp)
    nch = dyn_z.shape[0]
    # Gộp kênh để quét DM nhanh, nhưng phải GIỮ ĐỦ KÊNH: gộp quá tay làm
    # trải nội kênh lớn → mất độ phân giải DM (đã gặp: 64 kênh gộp 8× còn 8).
    TARGET_CH = 128
    rb = max(1, min(rebin, nch // TARGET_CH)) if nch > TARGET_CH else 1
    nnew = nch // rb
    # Q1: gộp kênh theo KHỐI, float32 — không tạo bản sao (nchan, ntime, rb)
    # float64 (đã gặp MemoryError 10 GiB với file 4096 kênh × 82k mẫu).
    dyn_rb = rebin_channels(dyn_z[: nnew * rb], rb)
    f_rb = f_g[: nnew * rb].reshape(nnew, rb).mean(axis=1)
    m["stage"]["rebin"] = rb
    print(f"→ gộp {rb}× → {nnew} kênh ({np.diff(f_rb).mean()*1e3:.0f} kHz/kênh)")

    # ---------------- A8: quét DM
    # Nếu biết P catalogue và đủ chu kỳ → quét DM bằng FOLD (nhạy gấp nhiều
    # lần: cộng dồn mọi xung). Nếu không (dữ liệu xung đơn) → lọc khớp boxcar.
    # Chọn chế độ quét DM theo SỐ CHU KỲ trong dữ liệu:
    #   ≥10 chu kỳ → fold (tích luỹ, nhạy với pulsar yếu/đều);
    #   < 10 chu kỳ → boxcar (nhạy với xung đơn/giant pulse).
    # 0.2 s dữ liệu Cua = 6 chu kỳ → boxcar (đúng: một giant pulse).
    # 4.2 s dữ liệu tiêm = 125 chu kỳ → fold (đúng: chuỗi xung đều).
    use_fold_scan = (p_ref is not None and h["t_s"] >= 10.0 * p_ref)
    # dm_max TỰ MỞ RỘNG theo mốc tham chiếu: nếu để mặc định 60 thì Vela (DM 68)
    # và B1641-45 (DM 479) sẽ bị quét thiếu — không bao giờ thấy đỉnh DM.
    if dm_max is None:
        dm_max = max(100.0, 1.5 * float(dm_ref or 0.0))
    dm_max = float(dm_max)
    if dm_ref is not None and dm_ref > dm_max:
        print(f"→ ⚠ dm_max = {dm_max:.0f} < dm_ref = {dm_ref:.1f}: nới lên theo mốc")
        dm_max = 1.5 * dm_ref
    # dm_step TỰ NỚI khi dải DM rộng: B1641-45 (dm_max 718) ở bước 0,25 là 2.873
    # bước — chậm. Giữ tổng số bước ≤ ~1000 để GUI không bị "đứng" lâu.
    if dm_max > 200 and dm_max / dm_step > 1000:
        new_step = round(dm_max / 1000.0, 3)
        print(f"→ A8 tự nới bước DM: {dm_step} → {new_step} (dải {dm_max:.0f})")
        dm_step = new_step
    m["stage"]["dm_step"] = dm_step
    m["stage"]["dm_max"] = dm_max
    print(f"→ A8 dải DM: 0–{dm_max:.0f} (bước {dm_step})"
          + (f" · mốc tham chiếu {dm_ref:.2f}" if dm_ref else ""))
    dm_grid = np.arange(0.0, dm_max + dm_step, dm_step)
    widths = (2, 4, 8, 16, 32, 64)
    snr_dm = np.zeros(len(dm_grid))
    best_w = np.zeros(len(dm_grid), dtype=int)
    for i, dm in enumerate(dm_grid):
        s, _ = dedisperse(dyn_rb, f_rb, dm, tsamp)
        if use_fold_scan:
            pr, _ = fold(s, tsamp, p_ref, nbins=256)
            snr_dm[i] = profile_snr(pr)[0]
        else:
            z, w, _ = boxcar_snr(s, widths=widths)
            snr_dm[i] = z
            best_w[i] = w
    k = int(np.argmax(snr_dm))
    dm_best = float(dm_grid[k])

    # ---- ZERO-DM VETO: RFI băng rộng cho SNR cao NHẤT ở DM = 0 và giảm dần.
    # Pulsar thật: khử tán sắc đúng DM làm xung nét hơn → SNR tăng theo DM.
    snr_dm0 = float(snr_dm[0]) if abs(dm_grid[0]) < 1e-9 else None
    dm_ratio = (float(snr_dm[k]) / max(snr_dm0, 1e-9)
                if snr_dm0 is not None else float("nan"))
    # Veto 1: RFI băng rộng (SNR cao nhất ở DM=0 và không tăng khi khử tán sắc).
    # Veto 2: đỉnh rơi đúng DM≈0 → tín hiệu KHÔNG tán sắc ⇒ RFI nội địa,
    # không phải pulsar (pulsar thật luôn có DM > 0 đáng kể so với bước quét).
    dm_zero_peak = (dm_best <= dm_step / 2.0 and snr_dm[k] > 8.0)
    zero_dm_dominated = ((snr_dm0 is not None and dm_best > 0
                          and dm_ratio < 1.15 and snr_dm0 > 8.0)
                         or dm_zero_peak)
    m["stage"]["snr_zero_dm"] = None if snr_dm0 is None else round(snr_dm0, 2)
    m["stage"]["dm_ratio_vs_zero"] = None if np.isnan(dm_ratio) else round(dm_ratio, 2)
    m["stage"]["zero_dm_dominated"] = bool(zero_dm_dominated)
    if zero_dm_dominated:
        print(f"→ ⚠ RFI ZERO-DM: SNR ở DM=0 ({snr_dm0:.0f}) ≥ SNR đỉnh "
              f"({snr_dm[k]:.0f}, DM={dm_best:.1f}) — tỷ số {dm_ratio:.2f}. "
              f"Tín hiệu không tán sắc ⇒ KHÔNG phải pulsar.")
    scan_kind = "fold tại P catalogue" if use_fold_scan else "xung đơn (boxcar)"
    print(f"→ A8 quét DM kiểu [{scan_kind}]: đỉnh {snr_dm[k]:.1f}σ tại "
          f"DM = {dm_best:.2f} (bước {dm_step})")
    m["stage"]["dm_scan_kind"] = scan_kind
    m["stage"]["dm_scan_peak_snr"] = round(float(snr_dm[k]), 2)
    m["stage"]["dm_scan_best"] = dm_best

    # độ phân giải DM CỦA CHÍNH DỮ LIỆU (không phải của thuật toán):
    # dịch DM 1 đơn vị gây trễ = K·(1/f_lo²−1/f_hi²); không phân biệt được
    # khi trễ này vượt ~nửa bề rộng xung.
    delay_per_dm_ms = abs(K_DM * (1 / f_rb.min()**2 - 1 / f_rb.max()**2)) * 1e3
    if use_fold_scan:
        _s, _w, _ph = profile_snr(fold(s, tsamp, p_ref, nbins=256)[0])
        w50_est_ms = _w * (p_ref / 256.0) * 1e3
    else:
        w50_est_ms = (best_w[k] * tsamp * 1e3) if best_w[k] > 0 else 10.0
    dm_res_data = max(w50_est_ms / (2 * delay_per_dm_ms), dm_step)
    m["stage"]["dm_resolution_data"] = round(dm_res_data, 2)
    print(f"→ độ phân giải DM của DỮ LIỆU này: ±{dm_res_data:.2f} "
          f"(W={w50_est_ms:.1f} ms, {delay_per_dm_ms*1e3:.1f} µs/DM)")

    # ---------------- A7: khử tán sắc + tìm xung
    s_dd, dropped = dedisperse(dyn_rb, f_rb, dm_best, tsamp)
    pulses = [] if zero_dm_dominated else find_pulses(
        s_dd, tsamp, threshold=pulse_thresh,
        min_sep_s=3 * tsamp * max(widths))
    if zero_dm_dominated:
        print("→ bỏ qua tìm xung đơn: dữ liệu bị RFI zero-DM chiếm ưu thế")
    print(f"→ A7 tìm xung: {len(pulses)} xung > {pulse_thresh}σ")
    m["stage"]["n_pulses"] = len(pulses)

    # ---------------- A11c: DM từng xung + LỌC NHẤT QUÁN DM (chống RFI hẹp băng)
    # RFI hẹp băng sống sót bước zero-DM nhưng cho DM dải con vô nghĩa;
    # xung thật phải cho DM KHỚP với DM quét → đây là bộ lọc cuối cùng.
    dm_tol = max(3.0, 0.12 * dm_best, dm_res_data)
    dm_list, rejected = [], []
    # chỉ đo DM dải con cho TOP-N xung mạnh nhất: mỗi phép đo là một lần quét
    # dải con, với 200+ ứng viên sẽ rất chậm (đã gặp: 416 s cho 21 s dữ liệu)
    MAX_SUBBAND = 8
    pulses_for_dm = sorted(pulses, key=lambda x: -x.get("snr", 0))[:MAX_SUBBAND]
    if len(pulses) > MAX_SUBBAND:
        print(f"→ A11c: đo DM dải con cho {MAX_SUBBAND}/{len(pulses)} xung mạnh "
              f"nhất (phần còn lại giữ nguyên làm ứng viên)")
    for p in pulses_for_dm:
        try:
            r = subband_dm_single(dyn_z, f_g, tsamp, p["t_s"],
                                  window_s=0.05, nsub=8,
                                  dm_guess=dm_best,
                                  width_samples=max(2, p["width_samples"]))
            p["dm_sub"] = round(r["dm"], 3)
            p["dm_sub_err"] = round(r["dm_err"], 3)
            consistent = abs(r["dm"] - dm_best) <= dm_tol
            p["dm_consistent"] = bool(consistent)
            if consistent:
                dm_list.append(r["dm"])
            else:
                rejected.append(p)
        except Exception as e:
            p["dm_sub"] = None
            p["dm_consistent"] = False
            p["dm_error"] = repr(e)
            rejected.append(p)
            print(f"   ⚠ xung t={p['t_s']*1e3:.0f} ms: lỗi đo DM dải con: {e!r}")
    pulses_ok = [p for p in pulses if p.get("dm_consistent")]
    # xung chưa được đo DM dải con: coi là ứng viên "chưa xác nhận", không loại
    for p in pulses:
        p.setdefault("dm_consistent", None)
    print(f"→ A11c DM dải con (nhất quán ±{dm_tol:.1f}): "
          f"{len(pulses_ok)}/{len(pulses)} xung"
          + (f" | DM = {np.mean(dm_list):.2f} ± {np.std(dm_list):.2f}"
             if dm_list else ""))
    if rejected:
        print(f"   loại {len(rejected)} ứng viên không nhất quán DM (RFI hẹp băng)")

    # ---------------- KIỂM TRA CÙNG PHA THEO P (bằng chứng cuối)
    # Xung thật của cùng pulsar phải đến CÙNG PHA (mod P); RFI thì không.
    train = []
    if p_ref and pulses_ok:
        for p in pulses_ok:
            p["phase_ms"] = round((p["t_s"] % p_ref) * 1e3, 1)
        phases = np.array([p["phase_ms"] for p in pulses_ok])
        used_ph = np.zeros(len(phases), dtype=bool)
        for i in np.argsort(-np.array([p["snr"] for p in pulses_ok])):
            if used_ph[i]:
                continue
            grp = [j for j in range(len(phases))
                   if not used_ph[j]
                   and abs(phases[j] - phases[i]) < max(30.0, 3 * pulses_ok[i]["width_ms"])]
            for j in grp:
                used_ph[j] = True
            if len(grp) >= 2:
                train = [pulses_ok[j] for j in grp]
                break
        if train:
            phs = [p["phase_ms"] for p in train]
            print(f"→ CÙNG PHA (mod P = {p_ref*1e3:.1f} ms): {len(train)} xung tại "
                  f"pha {np.mean(phs):.1f} ± {np.std(phs):.1f} ms → XÁC NHẬN pulsar")
        else:
            print("→ không tìm được chuỗi xung cùng pha")
    m["stage"]["n_pulses_consistent"] = len(pulses_ok)
    m["stage"]["n_pulses_rejected_rfi"] = len(rejected)
    m["stage"]["dm_tolerance"] = round(dm_tol, 2)
    if dm_list:
        m["stage"]["dm_subband_mean"] = round(float(np.mean(dm_list)), 3)
        m["stage"]["dm_subband_std"] = round(float(np.std(dm_list)), 3)

    # ---------------- M3: DÒ CHU KỲ MÙ (FFT + cộng hài + sàng hài → Top-N)
    if search_period or p_ref is None:
        try:
            print(f"→ M3 dò chu kỳ mù (FFT): P {pmin_s*1e3:.1f}–{pmax_s*1e3:.0f} ms, "
                  f"top {top_n}")
            _res = per.blind_period_search(
                s_dd, tsamp, fmin_hz=1.0 / pmax_s, fmax_hz=1.0 / pmin_s,
                nharm=4, top=top_n, threshold=pulse_thresh)
            m["period_search"] = {k: v for k, v in _res.items()
                                  if k not in ("profile",)}
            if _res.get("best"):
                _b = _res["best"]
                print(f"   ✓ ứng viên mạnh nhất: P = {_b['p_s']*1e3:.3f} ms "
                      f"(SNR {_b['snr']:.1f} ≥ {pulse_thresh:.0f})")
                for _c in _res["candidates"][:5]:
                    print(f"      P={_c['p_s']*1e3:9.3f} ms  SNR={_c['snr']:6.1f}")
            else:
                print(f"   (không có ứng viên vượt {pulse_thresh:.0f}σ sau khi sàng hài)")
        except Exception as _e:                   # noqa: BLE001
            m["period_search"] = dict(searched=False, error=repr(_e))
            print(f"   ⚠ M3 lỗi: {_e!r}")

    # ---------------- V2: kiểm chứng ĐẦU RA
    checks = []
    if dm_ref is not None:
        if m["stage"].get("dm_train_mean") is not None:
            dme = m["stage"]["dm_train_mean"]
            src = "chuỗi xung cùng pha"
        elif m["stage"].get("dm_subband_mean") is not None:
            dme = m["stage"]["dm_subband_mean"]
            src = "xung nhất quán"
        else:
            dme = dm_best
            src = f"quét DM kiểu {scan_kind}"
        err = abs(dme - dm_ref)
        tol = max(1.5, 0.06 * dm_ref)
        if dm_res_data > 0.25 * dm_ref:
            # dữ liệu KHÔNG đủ phân giải DM (băng hẹp, xung rộng): kiểm chứng
            # DM trở nên vô nghĩa — không được báo FAIL oan.
            checks.append(dict(
                name="DM vs tham chiếu", ok=True,
                detail=f"KHÔNG ÁP DỤNG: độ phân giải DM của dữ liệu "
                       f"±{dm_res_data:.0f} > 25% DM tham chiếu "
                       f"({dm_ref:.1f}); cần băng thông rộng hơn để đo DM"))
        else:
            checks.append(dict(name=f"DM vs tham chiếu ({src})",
                               ok=err < tol,
                               detail=f"đo {dme:.2f} vs {dm_ref:.3f} "
                                      f"(lệch {err:.2f}, ngưỡng {tol:.1f})"))
    if p_ref and len(pulses_ok) < 2:
        checks.append(dict(name="chuỗi xung cùng pha (mod P)", ok=True,
                           detail="KHÔNG ÁP DỤNG: chỉ 1 xung (giant pulse đơn lẻ) "
                                  "— nhịp đều đã kiểm qua fold tại P"))
    elif p_ref and train:
        phs = [p["phase_ms"] for p in train]
        checks.append(dict(name="chuỗi xung cùng pha (mod P)", ok=len(train) >= 2,
                           detail=f"{len(train)} xung tại pha {np.mean(phs):.1f} ± "
                                  f"{np.std(phs):.1f} ms (P = {p_ref*1e3:.1f} ms)"))
    elif p_ref and not pulses_ok:
        # dữ liệu kiểu FOLD (xung đơn yếu dưới ngưỡng) — fold sẽ chịu trách nhiệm
        checks.append(dict(name="chuỗi xung cùng pha (mod P)", ok=True,
                           detail="bỏ qua: không có xung đơn trên ngưỡng "
                                  "(bình thường với dữ liệu fold)"))
    elif p_ref:
        checks.append(dict(name="chuỗi xung cùng pha (mod P)", ok=False,
                           detail="có ứng viên nhưng không thành chuỗi cùng pha "
                                  "(nghi RFI)"))
    m["stage"]["n_pulses_in_train"] = len(train)
    if train:
        dm_t = [p["dm_sub"] for p in train if p.get("dm_sub") is not None]
        if dm_t:
            m["stage"]["dm_train_mean"] = round(float(np.mean(dm_t)), 3)
            m["stage"]["dm_train_std"] = round(float(np.std(dm_t)), 3)
    if pulses_ok:
        sp = sorted((p["t_s"] for p in pulses_ok), reverse=True)
        gaps = [sp[i] - sp[i + 1] for i in range(len(sp) - 1)]
        det = (f"{len(pulses_ok)} xung nhất quán DM"
               + (f", khe thời gian {[round(g*1e3) for g in gaps]} ms"
                  if gaps else ""))
        # Giant pulse: 1 xung là ĐÚNG. Dữ liệu dài ≥ 2.5 chu kỳ mà chỉ có 1
        # xung thì KHÔNG coi là FAIL (có thể là giant pulse đơn lẻ); nhịp đều
        # được kiểm tra riêng qua fold tại P và qua check "chuỗi cùng pha".
        n_p = len(pulses_ok)
        if p_ref and h["t_s"] > 2.5 * p_ref and n_p == 1:
            det += (f"; dữ liệu dài {h['t_s']/p_ref:.1f} chu kỳ nhưng chỉ 1 xung"
                    f" — phù hợp giant pulse đơn lẻ")
        checks.append(dict(name="xung thật (nhất quán DM)", ok=n_p >= 1, detail=det))
    # đối chứng nền: xáo TRỘN TỪNG KÊNH (phá liên kết liên tần số → phá vệt
    # tán sắc, giữ nguyên thống kê mỗi kênh). Không được cho SNR cao.
    rng = np.random.default_rng(0)
    shuffled = np.empty_like(dyn_rb)
    for i in range(dyn_rb.shape[0]):
        shuffled[i] = dyn_rb[i, rng.permutation(dyn_rb.shape[1])]
    s_n, _ = dedisperse(shuffled, f_rb, dm_best, tsamp)
    z_n, _, _ = boxcar_snr(s_n, widths=widths)
    checks.append(dict(name="đối chứng nền (trộn thời gian)",
                       ok=z_n < 12.0,
                       detail=f"SNR nền {z_n:.1f} (phải < 12; xung thật "
                              f"{snr_dm[k]:.0f})"))
    fold_info = None
    if p_ref is not None and h["t_s"] > 5 * p_ref:
        prof_f, _ = fold(s_dd, tsamp, p_ref, nbins=256)
        sfp = profile_snr(prof_f)[0]
        fold_info = dict(prof=prof_f, snr=sfp, p_s=p_ref, nbins=256,
                         cycles=h["t_s"] / p_ref)
        checks.append(dict(name="fold tại P catalogue", ok=sfp > 8.0,
                           detail=f"SNR fold = {sfp:.1f}"))
    else:
        checks.append(dict(name="fold tại P catalogue", ok=True,
                           detail=f"bỏ qua: file chỉ {h['t_s']:.1f} s "
                                  f"< 5×P — dữ liệu thiết kế cho xung đơn"))
    _ps = m.get("period_search") or {}
    if _ps.get("searched"):
        _b = _ps.get("best")
        checks.append(dict(
            name="dò chu kỳ mù (FFT + sàng hài)",
            ok=True,
            detail=(f"P = {_b['p_s']*1e3:.3f} ms, SNR {_b['snr']:.1f} "
                    f"(Top-N: {len(_ps.get('candidates') or [])} ứng viên)"
                    if _b else
                    f"không có ứng viên > {_ps.get('threshold', 8):.0f}σ "
                    f"({len(_ps.get('candidates') or [])} ứng viên xét)")))
    if m["stage"].get("zero_dm_dominated"):
        checks.append(dict(name="không bị RFI zero-DM chiếm ưu thế", ok=False,
                           detail=f"SNR(DM=0) = {m['stage']['snr_zero_dm']}, "
                                  f"tỷ số {m['stage']['dm_ratio_vs_zero']} < 1.15 "
                                  f"⇒ RFI băng rộng, không phải pulsar"))
        m["status"] = "rfi_zero_dm"
    m["output_checks"] = checks
    for c in checks:
        print(f"   [{'OK' if c['ok'] else 'FAIL'}] {c['name']}: {c['detail']}")
    m["output_ok"] = all(c["ok"] for c in checks)

    # ---------------- metrics chi tiết từng xung
    m["pulses"] = [{k: (round(v, 4) if isinstance(v, float) else v)
                    for k, v in p.items()} for p in pulses]
    m["dm_grid"] = [round(float(x), 3) for x in dm_grid[:: max(1, len(dm_grid)//200)]]
    m["snr_dm_curve"] = [round(float(x), 2) for x in snr_dm[:: max(1, len(dm_grid)//200)]]

    # ================= HÌNH 1: waterfall thô + đã khử tán sắc
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(2, 1, figsize=(9.2, 7.2))
    _src1 = (h.get("source") or "").strip()
    if _src1.lower() in ("", "temp", "unknown", "none", "test", "empty"):
        _src1 = os.path.splitext(os.path.basename(path))[0]
    # dựng lại waterfall đã khử tán sắc (DỊCH SỚM từng kênh:
    # output[j] = input[j+shift] — dịch muộn sẽ làm vệt CÒN CONG HƠN)
    from psr_core import dm_delay_s
    shifts = np.rint(dm_delay_s(dm_best, f_g, f_ref_mhz=f_g.max()) / tsamp).astype(int)
    ntt = dyn_z.shape[1]
    # CHỈ giữ vùng thời gian HỢP LỆ cho mọi kênh: nếu để nguyên, phần đuôi
    # (không đủ mẫu để dịch) toàn số 0 → -120 dB → mảng đen giả tạo trên hình.
    n_valid = max(1, ntt - int(np.max(shifts)))
    dyn_dd = np.zeros((dyn_z.shape[0], n_valid))
    for i, sh in enumerate(shifts):
        dyn_dd[i, :] = dyn_z[i, sh: sh + n_valid]
    pp.plot_waterfall(dyn_z[:, :n_valid], f_g, tsamp, ax=ax[0],
                      title=f"(a) Waterfall CHƯA khử tán sắc — {_src1}, "
                            f"{f_g.min():.0f}–{f_g.max():.0f} MHz, "
                            f"tsamp = {tsamp*1e6:.0f} µs")
    pp.plot_waterfall(dyn_dd, f_g, tsamp, ax=ax[1],
                      title=f"(b) ĐÃ khử tán sắc — DM = {dm_best:.2f} "
                            f"pc cm$^{{-3}}$")
    fig.tight_layout()
    pp.finalize(fig)
    f1 = os.path.join(out_dir, "fig1_overview.png")
    _savefig(fig, f1); plt.close(fig)

    # ================= HÌNH 2: 4 panel phát hiện
    fig, ax = plt.subplots(2, 2, figsize=(12.0, 8.2))
    t_all = np.arange(len(s_dd)) * tsamp
    pp.plot_timeseries(t_all, (s_dd - np.median(s_dd)),
                       peaks=pulses_ok, ax=ax[0, 0],
                       ylabel="công suất dư (đ.v. chuẩn hoá)",
                       title="(a) Chuỗi thời gian sau khử tán sắc")
    _scan_title = ("(b) Quét DM — fold tại P" if use_fold_scan
                   else "(b) Quét DM — boxcar đa độ rộng")
    _detected = float(snr_dm[k]) >= pulse_thresh
    if not _detected:
        _scan_title += f" — KHÔNG phát hiện (đỉnh {snr_dm[k]:.1f}σ < {pulse_thresh:.0f}σ)"
    pp.plot_dm_curve(dm_grid, snr_dm,
                     dm_meas=dm_best if _detected else None, dm_true=dm_ref,
                     ax=ax[0, 1], title=_scan_title, threshold=pulse_thresh)
    prof_show = s_dd - np.median(s_dd)
    met = {"width_ms": pulses_ok[0]["width_ms"] if pulses_ok else None}
    # panel (c): CẬN CẢNH quanh xung (trước đây vẽ cả chuỗi nhưng lại ghi
    # "vùng xung" — sai mô tả và chú thích tràn khung)
    if pulses_ok:
        p0 = pulses_ok[0]
        w_ms = p0.get("width_ms") or 1.0
        t0_ms = p0["t_s"] * 1e3
        # cửa sổ cận cảnh: đủ rộng để thấy chân xung, đủ hẹp để KHÔNG lẫn
        # xung bên cạnh (trước đây W50 = 8 ms → ±82 ms, lẫn cả 3 xung)
        hw = float(min(max(3.5 * w_ms, 3.0), 30.0))
        t_ms = t_all * 1e3
        sel = (t_ms >= t0_ms - hw) & (t_ms <= t0_ms + hw)
        if sel.sum() < 8:                      # dự phòng: cửa sổ quá hẹp
            hw = max(hw, 3.0 * w_ms + 5.0)
            sel = (t_ms >= t0_ms - hw) & (t_ms <= t0_ms + hw)
        pk_in = [p for p in pulses_ok if abs(p["t_s"] * 1e3 - t0_ms) <= hw]
        pp.plot_pulse_profile(t_ms[sel], prof_show[sel], pk_in[:3], met,
                              ax=ax[1, 0], xlim_ms=(t0_ms - hw, t0_ms + hw),
                              title=f"(c) Cận cảnh xung (±{hw:.1f} ms)")
    elif fold_info is not None and fold_info["snr"] > 8.0:
        pp.plot_fold_profile(fold_info, ax=ax[1, 0],
                             title="(c) Hồ sơ fold tại P tham chiếu")
    else:
        _rej = [p for p in pulses if p.get("dm_consistent") is False]
        if _rej:
            _ttl = f"(c) SNR theo thời gian — {len(_rej)} ứng viên bị loại (DM lệch)"
        else:
            _ttl = "(c) SNR theo thời gian — không mẫu nào vượt ngưỡng"
        _note = ""
        pp.plot_boxcar_snr(s_dd, tsamp, threshold=pulse_thresh, ax=ax[1, 0],
                           candidates=_rej or None, note=_note, title=_ttl)
    if pulses_ok and pulses_ok[0].get("dm_sub") is not None:
        r = subband_dm_single(dyn_z, f_g, tsamp, pulses_ok[0]["t_s"],
                              window_s=0.05, nsub=8, dm_guess=dm_best,
                              width_samples=max(2, pulses_ok[0]["width_samples"]))
        lags_rel = (r["lags_s"] - r["lags_s"][-1]) * 1e3    # so với dải cao nhất
        pp.plot_subband_lags(r["freqs_mhz"], lags_rel,
                             r["dm"], r["dm_err"],
                             ax=ax[1, 1],
                             title=f"(d) Trễ dải con — xung t = "
                                   f"{pulses_ok[0]['t_s']*1e3:.1f} ms")
    elif fold_info is not None:
        pp.plot_fold_snr_vs_dm(dm_grid, snr_dm, fold_info, ax=ax[1, 1],
                               threshold=pulse_thresh,
                               title="(d) SNR fold theo DM (phóng quanh DM tốt nhất)")
    else:
        ax[1, 1].text(0.5, 0.5, "không tìm thấy xung riêng lẻ để đo trễ dải con",
                      ha="center", va="center", fontsize=9, color="0.35",
                      transform=ax[1, 1].transAxes)
        ax[1, 1].set_xticks([]); ax[1, 1].set_yticks([])
        ax[1, 1].set_xlabel("tần số trung bình dải con (MHz)")
        ax[1, 1].set_ylabel("trễ so với dải cao nhất (ms)")
        ax[1, 1].set_title("(d) Trễ dải con — không áp dụng")
    # tiêu đề chung: chỉ ghi nguồn + kính NẾU header có — không bịa tên kính
    tel = (h.get("telescope") or h.get("instrument") or "").strip()
    src = (h.get("source") or "").strip()
    if src.lower() in ("", "temp", "unknown", "none", "test", "empty"):
        src = os.path.splitext(os.path.basename(path))[0]
    supt = f"Phát hiện pulsar trên dữ liệu THẬT — {src}" + (f" ({tel})" if tel else "")
    fig.suptitle(supt, fontsize=11.5)
    fig.tight_layout()
    # KIỂM TRA BỐ CỤC bằng hình học thật: chú giải đè dữ liệu / chữ tràn khung
    fig_issues = pp.finalize(fig)
    m["figure_check"] = fig_issues
    if fig_issues:
        print(f"   ⚠ bố cục hình: {len(fig_issues)} vấn đề")
        for it in fig_issues:
            print(f"      [{it['kind']}] {it['panel']}: {it['detail']}")
    else:
        print("   ✔ bố cục hình: chú giải/chú thích không đè dữ liệu, không tràn khung")
    f2 = os.path.join(out_dir, "fig2_detection.png")
    _savefig(fig, f2); plt.close(fig)

    m["files"] = [os.path.basename(f1), os.path.basename(f2)]
    # ---- M3: hình dò chu kỳ mù (nếu có ứng viên)
    try:
        _ps = m.get("period_search") or {}
        if _ps.get("best"):
            import psr_period as _per
            _b = _ps["best"]
            _prof, _ = fold(s_dd, tsamp, float(_b["p_s"]), nbins=256)
            _ps2 = dict(_ps)
            _ps2["profile"] = _prof
            _figp, _axp = plt.subplots(1, 2, figsize=(11.0, 3.4))
            _per.plot_period_search(_ps2, ax=_axp)
            _figp.tight_layout()
            pp.finalize(_figp)
            _f3 = os.path.join(out_dir, "fig3_period.png")
            _savefig(_figp, _f3)
            plt.close(_figp)
            m["files"].append(os.path.basename(_f3))
            print(f"→ hình dò chu kỳ: {os.path.basename(_f3)}")
    except Exception as _e:                        # noqa: BLE001
        print(f"   ⚠ không vẽ được hình chu kỳ: {_e!r}")
    guard.atomic_write_json(os.path.join(out_dir, "detect_metrics.json"),
                            _jsonify(m))       # Q2: ghi nguyên tử

    # ---------------- báo cáo chữ
    rep = []
    rep.append("BÁO CÁO PHÁT HIỆN PULSAR — DỮ LIỆU THẬT")
    rep.append(f"File: {path}")
    rep.append(f"Nguồn: {h['source']} | {h['nchans']} kênh | "
               f"{freqs.min():.1f}–{freqs.max():.1f} MHz | {h['t_s']:.2f} s | "
               f"tsamp {tsamp*1e6:.0f} µs")
    rep.append(f"Kênh giữ/cắt: {good.sum()}/{(~good).sum()} | "
               f"mẫu zero-DM cắt: {bad_t.sum()} ({100*bad_t.mean():.1f}%)")
    rep.append(f"DM (quét): {dm_best:.2f} | DM (dải con): "
               f"{m['stage'].get('dm_subband_mean', float('nan')):.2f} ± "
               f"{m['stage'].get('dm_subband_std', float('nan')):.2f}"
               + (f" | tham chiếu: {dm_ref}" if dm_ref else ""))
    rep.append(f"Số xung phát hiện: {len(pulses)} | nhất quán DM: {len(pulses_ok)} | "
               f"loại RFI hẹp băng: {len(rejected)}")
    for i, p in enumerate(pulses_ok):
        rep.append(f"  xung {i+1}: t = {p['t_s']*1e3:.1f} ms, SNR = {p['snr']:.1f}, "
                   f"bề rộng = {p['width_ms']:.1f} ms, "
                   f"DM dải con = {p.get('dm_sub')}")
    rep.append("Kiểm chứng đầu ra:")
    for c in checks:
        rep.append(f"  [{'OK' if c['ok'] else 'FAIL'}] {c['name']}: {c['detail']}")
    report = "\n".join(rep)
    with open(os.path.join(out_dir, "detect_report.txt"), "w",
              encoding="utf-8") as fh:
        fh.write(report + "\n")
    print("\n" + report)
    print(f"\n→ THƯ MỤC KẾT QUẢ: {out_dir}")
    print(f"   fig1_overview.png, fig2_detection.png, "
          f"detect_metrics.json, detect_report.txt")
    return m


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default=os.path.join(DATA, "B0329+54.fil"))
    # Mặc định KHÔNG có mốc: mốc chỉ dùng khi người dùng đưa vào hoặc khi
    # nhận ra mục tiêu từ tên file/header (tra psr_targets). Đặt mốc cứng
    # của B0329+54 từng làm dữ liệu Cua bị so sai (26.76 vs 56.77).
    ap.add_argument("--dm-ref", type=float, default=None,
                    help="DM tham chiếu (pc cm^-3), chỉ để KIỂM CHỨNG")
    ap.add_argument("--p", type=float, default=None,
                    help="chu kỳ tham chiếu (s), chỉ để fold kiểm chứng")
    ap.add_argument("--dm-max", type=float, default=None,
                    help="mặc định: max(100, 1.5×dm_ref)")
    ap.add_argument("--dm-step", type=float, default=0.25)
    ap.add_argument("--thresh", type=float, default=8.0)
    ap.add_argument("--search-period", action="store_true",
                    help="luôn dò chu kỳ mù (mặc định chỉ khi không có P)")
    ap.add_argument("--pmin-ms", type=float, default=1.5)
    ap.add_argument("--pmax-s", type=float, default=10.0)
    ap.add_argument("--top-n", type=int, default=10)
    a = ap.parse_args()
    ensure_utf8_stdout()
    detect(a.file, dm_ref=a.dm_ref, p_ref=a.p, dm_max=a.dm_max,
           search_period=a.search_period, pmin_s=a.pmin_ms / 1e3,
           pmax_s=a.pmax_s, top_n=a.top_n,
           dm_step=a.dm_step, pulse_thresh=a.thresh)
