# -*- coding: utf-8 -*-
"""psr_rtcs.py — Đọc & phân tích DỮ LIỆU XUẤT CỦA RTCS (POAM RTP-37).

RTCS xuất **văn bản**, không xuất IQ:
  · line.csv / Line observation.txt  → Frequency (Hz) | Power (dBm)
  · continuum observation.txt/.csv   → Time (s) | dBm từng receiver (RTRS 1..8)
  · log Scan (vd 123.txt)            → AZ-deg | EL-deg | RTRS1 (dBm)

Tốc độ lấy mẫu ≤ 10 Hz và phổ đã tích phân ⇒ các tệp này **không dùng được cho
pulsar** (mất pha). Module phục vụ đúng mục đích của chúng: hiệu chuẩn hệ thống,
đo búp sóng thực tế, khảo sát RFI, kiểm tra chuỗi thu.

Công thức hiệu chuẩn theo **Appendix A** (RTCS v2.2, tr.49):
    Tn   = (Tamb − 24)·0.1 + ENR + 273.5            [K]   (ENR nhập bằng °C)
    T_A  = (P_sun − P_sky) / [(P_n − P_load)/(Tn − T_load)]     [K]
    T_sys= P_sky / [(P_n − P_load)/(Tn − T_load)] − T_sky_ant   [K]
    SEFD = 2k·T_sys / A_eff                                    [Jy]
    SFD  = 2k·T_A·e^τ·10^(L/10) / (α·A_CE)                     [Jy]
Mọi tỉ số công suất tính trên giá trị TUYẾN TÍNH (đổi từ dBm).

KHÔNG sửa/không import ngược psr_core, psr_detect: lõi pulsar v1.5.0 giữ nguyên.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys

import numpy as np

K_B = 1.380649e-23
JY = 1e26
FWHM_PER_SIGMA = 2.3548200450309493


# ---------------------------------------------------------------- tiện ích
def dbm_to_mw(p_dbm):
    """dBm → mW (tuyến tính)."""
    return 10.0 ** (np.asarray(p_dbm, dtype=float) / 10.0)


def _num(s) -> float | None:
    """Đọc số: chịu được dấu phẩy thập phân, khoảng trắng, '.55'."""
    s = str(s or "").strip().replace("\u00a0", " ")
    if not s:
        return None
    s = s.replace(" ", "")
    if s.count(",") == 1 and "." not in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _meta_from_text(txt: str) -> dict:
    """Bóc header RTCS: RTRS: "RTRS1", IQ Rate=…, Samples=…, Carrier Freq.=…"""
    meta: dict = {}
    m = re.search(r"RTRS\s*:\s*(.+)$", txt, re.MULTILINE)
    if m:
        raw = m.group(1).strip()
        meta["rtcs_raw"] = raw
        for key, pat, cast in (
                ("rtrs", r'"([^"]+)"', str),
                ("iq_rate_sps", r"IQ\s*Rate\s*=\s*([0-9.eE+-]+)", float),
                ("samples", r"Samples\s*=\s*([0-9.eE+-]+)", float),
                ("centre_hz", r"Carrier\s*Freq\.?\s*=\s*([0-9.eE+-]+)", float),
                ("gain_db", r"Gain\s*=\s*([0-9.eE+-]+)", float),
                ("bandwidth_hz", r"Bandwidth\s*=\s*([0-9.eE+-]+)", float)):
            mm = re.search(pat, raw)
            if mm:
                try:
                    meta[key] = cast(mm.group(1))
                except ValueError:
                    pass
    for key, pat in (("start_time", r"Start\s*Time\s+([0-9:APM.\s]+?)\s*$"),
                     ("end_time", r"End\s*Time\s+([0-9:APM.\s]+?)\s*$"),
                     ("longitude", r"Longitude\s+([-0-9.]+)"),
                     ("latitude", r"Latitude\s+([-0-9.]+)"),
                     ("date", r"(\d{1,2}/\d{1,2}/\d{4})")):
        mm = re.search(pat, txt, re.MULTILINE)
        if mm and mm.group(1).strip():
            v = mm.group(1).strip()
            meta[key] = _num(v) if key in ("longitude", "latitude") else v
    return meta


# ============================================================ 1) PHỔ (line)
def read_line(path: str) -> dict:
    """Đọc line.csv / Line observation.txt → {freqs_hz, power_dbm, meta}."""
    raw = open(path, encoding="utf-8", errors="replace").read()
    meta = _meta_from_text(raw)
    freqs, power = [], []
    for ln in raw.splitlines():
        c = [x for x in re.split(r"[	;,]", ln) if x.strip() != ""]
        if len(c) < 2:
            continue
        f, p = _num(c[0]), _num(c[1])
        if f is None or p is None:
            continue                      # dòng tiêu đề
        freqs.append(f)
        power.append(p)
    if not freqs:
        raise ValueError(f"{os.path.basename(path)}: không thấy cặp "
                         f"Frequency/Power")
    f = np.asarray(freqs, float)
    p = np.asarray(power, float)
    if f.max() < 1e7:                     # nếu ghi bằng MHz
        f = f * 1e6
    meta["n_bins"] = int(f.size)
    # Endpoint-inclusive grid spacing; keep median adjacent spacing separately.
    # Which is the physical FFT channel resolution depends on metadata/convention.
    meta["df_hz"] = float((f.max() - f.min()) / max(f.size - 1, 1)) if f.size > 1 else 0.0
    meta["df_hz_median"] = float(np.median(np.diff(f))) if f.size > 1 else 0.0
    meta["span_hz"] = float(f.max() - f.min()) if f.size > 1 else 0.0
    meta["centre_hz_meas"] = float(0.5 * (f.max() + f.min()))
    return dict(freqs_hz=f, power_dbm=p, meta=meta)


def spectrum_stats(f, p) -> dict:
    """Nền/RMS/peak và spacing theo quy ước grid endpoint-inclusive.

    Trả riêng span/(N−1) và median(diff). Cả hai đều là thống kê trên frequency
    values đã xuất; độ phân giải FFT vật lý cuối cùng cần metadata receiver.
    """
    med = float(np.median(p))
    rms = 1.4826 * float(np.median(np.abs(p - med))) or 1e-9
    k = int(np.argmax(p))
    n = int(f.size)
    # Thứ tự input CSV không được cam kết: Δf và bin N/2 chỉ có nghĩa sau
    # khi sắp tần số tăng dần; hoán vị cả frequency/power giữ nguyên cặp mẫu.
    if n > 1 and np.any(np.diff(f) < 0):
        order = np.argsort(f)
        f = np.asarray(f)[order]
        p = np.asarray(p)[order]
        k = int(np.argmax(p))
    span = float(f.max() - f.min())
    df_from_span = span / max(n - 1, 1)
    df_median = float(np.median(np.diff(f))) if n > 1 else 0.0
    meta = {}
    if n > 2 and df_median > 0 and abs(df_from_span - df_median) > 0.02 * df_from_span:
        meta["df_lam_bao_nhay"] = (
            f"median(diff)={df_median/1e3:.2f} kHz; endpoint-grid "
            f"span/(N−1)={df_from_span/1e3:.3f} kHz. Rounded frequency values "
            "or FFT bin convention may explain the difference; consult receiver metadata.")
    # Candidate centre-bin receiver artifact; position alone does not prove cause.
    dc = None
    if n >= 16:
        fc = 0.5 * (float(f.max()) + float(f.min()))
        kc = n // 2
        # FFT centering conventions vary; include a small set of central bins.
        cand = [i for i in range(max(0, kc-2), min(n, kc+2))]
        pk = float(p[k])
        near_centre = bool(cand) and k in cand
        w = max(3, n // 100)
        lo_i, hi_i = max(0, k - w), min(n, k + w + 1)
        is_local_max = bool(pk >= float(np.max(p[lo_i:hi_i])))
        if near_centre and is_local_max and (pk - med) > 2.0 * rms:
            dc = dict(bin=k, hz=float(f[k]), dbm=pk, delta_db=float(pk - med),
                      sigma=float((pk - med) / rms), centre_hz=fc,
                      offset_hz=float(abs(float(f[k]) - fc)),
                      n_bins=len(cand))
    return dict(median_dbm=med, rms_db=rms, peak_dbm=float(p[k]),
                peak_hz=float(f[k]), peak_bin=int(k),
                peak_snr_db=float((p[k] - med) / rms),
                span_mhz=float(span / 1e6), df_khz=float(df_from_span / 1e3),
                df_khz_median=float(df_median / 1e3), n_bins=n,
                centre_hz=0.5 * (float(f.max()) + float(f.min())),
                dc_leak=dc, note_df=meta.get("df_lam_bao_nhay", ""))


# ========================================================= 2) CONTINUUM
def read_continuum(path: str) -> dict:
    """Đọc continuum observation.* → {t_s, rx:{nhãn: dBm}, meta, labels}.

    Cột: `Time - RTRS n | dBm - RTRS n | …`. Giá trị **0.0 = không có dữ liệu**
    (RTCS ghi 0) → đổi thành NaN để không kéo lệch trung bình/độ trôi.
    """
    raw = open(path, encoding="utf-8", errors="replace").read()
    meta = _meta_from_text(raw)
    head, rows = None, []
    for ln in raw.splitlines():
        c = [x.strip() for x in re.split(r"[	;,]", ln)]
        if head is None:
            if any("Time" in x for x in c) and any("dBm" in x for x in c):
                head = c
            continue
        vals = [_num(x) for x in c]
        if any(v is not None for v in vals):
            rows.append(vals)
    if head is None or not rows:
        raise ValueError(f"{os.path.basename(path)}: không thấy header "
                         f"'Time - RTRS n | dBm - RTRS n'")
    labels = []
    for i in range(0, len(head) - 1, 2):
        lab = head[i + 1].replace("dBm -", "").replace("dBm-", "").strip()
        labels.append(lab or f"RTRS{i//2+1}")
    n = len(labels)
    t = np.full(len(rows), np.nan)
    data = np.full((n, len(rows)), np.nan)
    for r, vals in enumerate(rows):
        for i in range(n):
            it, ip = 2 * i, 2 * i + 1
            if it < len(vals) and vals[it] is not None and np.isnan(t[r]):
                t[r] = vals[it]
            if ip < len(vals) and vals[ip] is not None:
                v = vals[ip]
                data[i, r] = np.nan if v == 0.0 else v
    order = np.argsort(np.nan_to_num(t, nan=1e18))
    return dict(t_s=t[order], rx={lab: data[i][order] for i, lab in enumerate(labels)},
                labels=labels, meta=meta)


def detrend(t, y, robust: bool = True) -> dict:
    """Khử trôi tuyến tính (gain drift) + trả tốc độ trôi (dB/phút)."""
    out = np.array(y, dtype=float)
    ok = np.isfinite(t) & np.isfinite(y)
    if ok.sum() < 3:
        return dict(y=out, slope_db_per_min=float("nan"),
                    p2p_db=float("nan"), n=int(ok.sum()))
    x, v = t[ok].astype(float), y[ok].astype(float)
    for _ in range(3 if robust else 0):
        a, b = np.polyfit(x, v, 1)
        res = v - (a * x + b)
        s = 1.4826 * float(np.median(np.abs(res - np.median(res)))) or 1e-9
        keep = np.abs(res) < 3.0 * s
        if keep.sum() < max(5, int(0.5 * x.size)):
            break
        x, v = x[keep], v[keep]
    a, b = np.polyfit(x, v, 1)
    out[ok] = y[ok] - (a * t[ok] + b) + float(np.median(v))
    fin = out[np.isfinite(out)]
    return dict(y=out, slope_db_per_min=float(a * 60.0),
                p2p_db=float(np.percentile(fin, 99) - np.percentile(fin, 1))
                if fin.size else float("nan"), n=int(x.size))


# ============================================================== 3) SCAN
def segment_series(t, y, jump_db: float = 12.0, min_len: int = 8) -> list:
    """Tách baseline/plateau từ mức công suất; không tự gán nguyên nhân NCU.

    Median filter 9 samples và debounce min_len theo số mẫu (RTCS cadence có thể
    là 0.1/1/10 s). Nhãn plateau/baseline là state thống kê; xác nhận NCU cần log
    trạng thái đồng bộ. Trả dict segment gồm index, time, level, MAD và kind.
    """
    t, y = np.asarray(t, float), np.asarray(y, float)
    ok = np.isfinite(t) & np.isfinite(y)
    idx = np.flatnonzero(ok)
    if idx.size < 3:
        return []
    smooth = np.full(y.size, np.nan)
    half = 4
    for i in idx:
        lo, hi = max(0, int(i)-half), min(y.size, int(i)+half+1)
        v = y[lo:hi]
        v = v[np.isfinite(v)]
        if v.size:
            smooth[i] = np.median(v)
    base = float(np.median(smooth[np.isfinite(smooth)]))
    high = np.isfinite(smooth) & (smooth > base + jump_db)
    runs=[]; start=int(idx[0]); state=bool(high[start])
    for ii in idx[1:]:
        i=int(ii); curr=bool(high[i])
        if curr != state and i-start >= min_len:
            runs.append((start,i,state)); start,state=i,curr
    runs.append((start,int(idx[-1])+1,state))
    merged=[]
    for i0,i1,st in runs:
        if i1-i0 < min_len and merged:
            a0,_,st0=merged[-1]; merged[-1]=(a0,i1,st0)
        else:
            merged.append((i0,i1,st))
    out=[]
    for i0,i1,st in merged:
        sl=idx[(idx>=i0)&(idx<i1)]
        if sl.size < 3: continue
        vals=y[sl]; med=float(np.median(vals))
        mad=1.4826*float(np.median(np.abs(vals-med)))
        out.append(dict(i0=int(sl[0]),i1=int(sl[-1]+1),n=int(sl.size),
                        level_dbm=med,mad_db=mad,t0=float(t[sl[0]]),
                        t1=float(t[sl[-1]]),kind='plateau' if st else 'baseline'))
    return out

def drift_segments(t, y, jump_db: float = 12.0) -> dict:
    """Đo độ dốc chuỗi và riêng đoạn baseline sau khi tách bậc công suất.

    Trả {slope_naive, segments, slope_best_db_per_min, best_segment, note}.
    Baseline/plateau là phân lớp thống kê theo mức công suất; không tự quy
    nguyên nhân cho NCU nếu thiếu log trạng thái đồng bộ.
    """
    naive = detrend(t, y, robust=True)
    segs = segment_series(t, y, jump_db=jump_db)
    best, best_len, best_span = float("nan"), 0, None
    for o in segs:
        if o["n"] < 30 or o["kind"] != "baseline":
            continue
        # Nếu baseline dài bắt đầu sau một bước nhảy, rolling window đã để
        # lại vài mẫu nhiễm biên; lùi đầu đoạn đến khi level vào plateau.
        i0, i1 = o["i0"], o["i1"]
        # Rolling median may mark a transition a few samples late; the raw
        # baseline level tells whether the immediately previous sample belongs.
        centre = float(np.median(y[i0:i1]))
        while i0 > 0 and np.isfinite(y[i0-1]) and abs(float(y[i0-1])-centre) <= jump_db:
            i0 -= 1
        d = detrend(t[i0:i1], y[i0:i1], robust=False)
        if o["n"] > best_len and np.isfinite(d["slope_db_per_min"]):
            best_len, best, best_span = int(o["n"]), d["slope_db_per_min"], o
    note = ""
    if segs and best_span is None:
        note = ("không có đoạn baseline nào ≥30 mẫu để đo slope; dữ liệu quá ngắn "
                "hoặc chỉ có một state công suất")
    elif best_span is not None and np.isfinite(naive["slope_db_per_min"]) \
            and abs(naive["slope_db_per_min"] - best) > 0.5:
        note = (f"độ dốc toàn chuỗi ({naive['slope_db_per_min']:+.3f} dB/phút) "
                f"bị ảnh hưởng bởi các bước nhảy; baseline dài {best_len} mẫu "
                f"có slope {best:+.4f} dB/phút. Chưa xác định nguồn bước nhảy "
                "nếu thiếu log state/Calibrator đồng bộ.")
    return dict(slope_naive=float(naive["slope_db_per_min"]),
                segments=segs, n_segments=len(segs),
                slope_best_db_per_min=float(best),
                best_segment=best_span, note=note,
                sigma_db_naive=float(naive["p2p_db"]))


def allan_deviation(y, dt_s: float, taus=(1, 4, 16, 64, 128)) -> dict:
    """Độ lệch Allan trên đoạn nền — phân biệt nhiễu trắng vs 1/f.

    Vì sao cần (kiểm toán §4.2): nếu σ_A giảm đúng τ^-1/2 tới > 100 s thì hệ
    CHƯA chạm sàn 1/f → tích luỹ dài có lợi; ngược lại nếu phẳng/sụt chậm thì
    có trôi độ lợi. Kèm đó so với σ của MỘT mẫu công suất đơn (5,57 dB lý
    thuyết cho χ²_2) để phát hiện RTCS không lấy trung bình nội khung.
    """
    y = np.asarray(y, float)
    y = y[np.isfinite(y)]
    out = {}
    nmax = y.size
    for tau in taus:
        k = max(1, int(round(tau)))
        if 2 * k >= nmax:
            continue
        # Allan phương sai cho mẫu trung bình khối liên tiếp
        blocks = y[:(nmax // k) * k].reshape(-1, k).mean(axis=1)
        if blocks.size < 2:
            continue
        av = 0.5 * float(np.mean(np.diff(blocks) ** 2))
        out[f"tau_{int(tau * dt_s)}s"] = float(np.sqrt(av))
    # σ của một mẫu đơn (phân bố mũ) để đối chiếu
    sig_tau = [v for k, v in out.items() if k.startswith("tau_")]
    out["sigma_single_sample_db"] = float(np.std(y))
    out["expected_chi2_2_db"] = 5.570           # 10/ln10 · π/√6
    # “giảm chuẩn τ^-1/2”: σ đoạn τ lớn nhất còn < nửa σ đoạn τ nhỏ nhất
    out["white_noise_slope_ok"] = bool(
        len(sig_tau) >= 2 and sig_tau[0] > 0
        and min(sig_tau) < 0.5 * sig_tau[0])
    return out


def read_scan(path: str) -> dict:
    """Đọc log quét → {az_deg, el_deg, power_dbm, meta, groups}.

    Groups mark only large AZ/EL coordinate discontinuities for QC; they are
    not asserted as seven scan passes or as one-dimensional beam cross-scans.
    Missing RTCS point timestamps/scan-state metadata prevent exact recovery
    of pass boundaries. HPBW is accepted only for a monotonic AZ/EL-stable slice.
    """
    raw = open(path, encoding="utf-8", errors="replace").read()
    meta = _meta_from_text(raw)
    az, el, pw = [], [], []
    started = False
    for ln in raw.splitlines():
        c = [x for x in re.split(r"[	;,]", ln) if x.strip() != ""]
        if not started:
            if len(c) >= 3 and all(_num(c[i]) is None for i in range(3)):
                started = True            # dòng tiêu đề 'AZ-deg EL-deg RTRS1'
            continue
        if len(c) < 3:
            continue
        a, e, p = _num(c[0]), _num(c[1]), _num(c[2])
        if a is None or e is None:
            a, e, p = _num(c[-3]), _num(c[-2]), _num(c[-1])
            if a is None or e is None:
                continue
        # Suffix AZ like .55 shows truncation but not the missing digits.
        # Keep it missing; do not infer the original coordinate from next row.
        if a is not None and a < 1.0 and c and c[0].strip().startswith("."):
            a = None
        az.append(a)
        el.append(e)
        pw.append(np.nan if (p is None or p == 0.0) else p)
    if not az:
        raise ValueError(f"{os.path.basename(path)}: không thấy dòng AZ/EL/power")
    a, e, p = (np.asarray(az, float), np.asarray(el, float),
               np.asarray(pw, float))
    # Không thể khôi phục chữ số đã cắt chỉ từ suffix (.55); giữ AZ=NaN.
    truncated = []
    # Re-read numeric rows only to record the truncated row index/suffix.
    data_lines = []
    _started = False
    for _ln in raw.splitlines():
        _c = [x for x in re.split(r"[\t;,]", _ln) if x.strip()]
        if not _started:
            if len(_c) >= 3 and all(_num(_c[j]) is None for j in range(3)):
                _started = True
            continue
        if len(_c) >= 3:
            data_lines.append(_c)
    for i, _c in enumerate(data_lines[:a.size]):
        if _c[0].strip().startswith(".") and i+1 < a.size:
            truncated.append(dict(index=i, suffix=_c[0].strip(),
                                  next_az=float(a[i+1]) if np.isfinite(a[i+1]) else None))
            a[i] = np.nan
    meta["truncated_az_rows"] = truncated
    meta["repaired_truncated_az"] = []  # compatibility: deliberately no repair
    meta["n_repaired"] = 0
    meta["n_truncated_az"] = len(truncated)
    meta["n_zero_samples"] = int(np.sum(~np.isfinite(p)))
    meta["frac_zero"] = float(np.mean(~np.isfinite(p))) if p.size else 0.0
    # Large AZ/EL jumps are QC discontinuities only. Export lacks per-point
    # timestamps and scan-state, so exact pass/row boundaries cannot be inferred.
    step = float("nan")
    d = np.abs(np.diff(a))
    dv = d[np.isfinite(d) & (d > 0)]
    if dv.size:
        cand = dv[(dv > 0.05) & (dv < 2.0)]
        step = float(np.median(cand)) if cand.size else float(np.median(dv))
    if not np.isfinite(step) or step <= 0:
        step = 0.5
    de = np.abs(np.diff(e))
    cuts = set(np.where(d > max(5.0 * step, 5.0))[0] + 1)
    cuts |= set(np.where(de > max(3.0 * step, 3.0))[0] + 1)
    cuts = sorted(int(c) for c in cuts if 0 < c < a.size)
    groups, start = [], 0
    for c in list(cuts) + [a.size]:
        if c - start >= 5:
            groups.append(slice(start, c))
        start = c
    return dict(az_deg=a, el_deg=e, power_dbm=p, meta=meta, groups=groups,
                step_deg=step)


def _gauss(x, amp, mu, sigma, b0, b1):
    return amp * np.exp(-0.5 * ((x - mu) / sigma) ** 2) + b0 + b1 * (x - mu)


def fit_gaussian_scan(x, y) -> dict:
    """Khớp Gauss + nền tuyến tính KHÔNG cần scipy (lưới σ + bình phương tối thiểu)."""
    ok = np.isfinite(x) & np.isfinite(y)
    if int(ok.sum()) < 7:
        return dict(ok=False, reason=f"chỉ {int(ok.sum())} điểm hợp lệ")
    x = np.asarray(x, float)[ok]
    y = np.asarray(y, float)[ok]
    o = np.argsort(x)
    x, y = x[o], y[o]
    span = float(x.max() - x.min())
    if span <= 0:
        return dict(ok=False, reason="dải quét bằng 0")
    mu0 = float(x[int(np.argmax(y))])
    best = None
    for sigma in np.linspace(max(span / 60.0, 0.01), span, 240):
        g = np.exp(-0.5 * ((x - mu0) / sigma) ** 2)
        A = np.vstack([g, np.ones_like(x), x - mu0]).T
        try:
            coef, *_ = np.linalg.lstsq(A, y, rcond=None)
        except np.linalg.LinAlgError:
            continue
        sse = float(np.sum((y - A @ coef) ** 2))
        if best is None or sse < best[0]:
            best = (sse, float(sigma), coef)
    if best is None:
        return dict(ok=False, reason="không khớp được")
    _, sigma, _ = best
    mus = np.linspace(mu0 - 2 * sigma, mu0 + 2 * sigma, 81)
    sses = []
    for mu in mus:
        g = np.exp(-0.5 * ((x - mu) / sigma) ** 2)
        A = np.vstack([g, np.ones_like(x), x - mu]).T
        coef, *_ = np.linalg.lstsq(A, y, rcond=None)
        sses.append(float(np.sum((y - A @ coef) ** 2)))
    j = int(np.argmin(sses))
    mu = float(mus[j])
    if 0 < j < len(sses) - 1:
        y0, y1, y2 = sses[j - 1], sses[j], sses[j + 1]
        den = y0 - 2 * y1 + y2
        if den != 0:
            mu += 0.5 * (y0 - y2) / den * float(mus[1] - mus[0])
    g = np.exp(-0.5 * ((x - mu) / sigma) ** 2)
    A = np.vstack([g, np.ones_like(x), x - mu]).T
    coef, *_ = np.linalg.lstsq(A, y, rcond=None)
    amp, b0, b1 = float(coef[0]), float(coef[1]), float(coef[2])
    res = y - A @ coef
    rms = float(np.sqrt(np.mean(res ** 2)))
    if amp <= 0:
        return dict(ok=False, reason="biên độ Gauss ≤ 0 (không có búp)")
    return dict(ok=True, amp_db=amp, mu=mu, sigma_deg=float(sigma),
                hpbw_deg=float(FWHM_PER_SIGMA * sigma), baseline_db=b0,
                baseline_slope_db_per_deg=b1, rms_db=rms, n_used=int(x.size),
                snr=float(amp / rms) if rms > 0 else float("inf"))


def scan_curve(scan: dict, group: int | None = None) -> dict:
    """Chọn trục quét (AZ/EL biến thiên nhiều hơn) cho một lượt."""
    sl = slice(None) if group is None else scan["groups"][group]
    a, e, p = scan["az_deg"][sl], scan["el_deg"][sl], scan["power_dbm"][sl]
    ra = float(np.nanmax(a) - np.nanmin(a))
    re_ = float(np.nanmax(e) - np.nanmin(e))
    axis = "az" if ra >= re_ else "el"
    return dict(axis=axis, x=(a if axis == "az" else e), y=p, az=a, el=e,
                centre=(float(np.nanmedian(a)), float(np.nanmedian(e))))


# ================================================ 4) HIỆU CHUẨN (Appendix A)
def tn_from_enr(tamb_c: float, enr_c: float) -> float:
    """RTCS Appendix A: Tn = (Tamb − 24)·0.1 + ENR + 273.5  [K]."""
    return (float(tamb_c) - 24.0) * 0.1 + float(enr_c) + 273.5


def tn_from_enr_db(tamb_c: float, enr_db: float, t0_k: float = 290.0) -> float:
    """Nếu ENR công bố bằng dB: Tn = Tamb + T0·(10^(ENR/10) − 1)."""
    return (float(tamb_c) + 273.15) + t0_k * (10 ** (float(enr_db) / 10.0) - 1.0)


def four_point_ta(p_sun_dbm, p_sky_dbm, p_n_dbm, p_load_dbm,
                  tn_k: float, t_load_k: float) -> dict:
    """T_A Mặt Trời (K) + độ lợi hệ [mW/K] từ 4 phép đo Appendix A."""
    ps, pk, pn, pl = (float(dbm_to_mw(v)) for v in
                      (p_sun_dbm, p_sky_dbm, p_n_dbm, p_load_dbm))
    if pn == pl:
        raise ValueError("P_noise = P_load → không xác định được độ lợi")
    g = (pn - pl) / (tn_k - t_load_k)
    return dict(ta_k=float((ps - pk) / g), gain_mw_per_k=float(g),
                y_noise_over_load=float(pn / pl) if pl else float("nan"))


def tsys_from_points(p_sky_dbm, p_n_dbm, p_load_dbm, tn_k: float,
                     t_load_k: float, t_sky_ant_k: float = 10.0) -> dict:
    """T_sys (K) từ nguồn chuẩn + tải hấp thụ, đo ở vị trí trời trống."""
    pk, pn, pl = (float(dbm_to_mw(v)) for v in (p_sky_dbm, p_n_dbm, p_load_dbm))
    if pn == pl:
        raise ValueError("P_noise = P_load → không xác định được độ lợi")
    g = (pn - pl) / (tn_k - t_load_k)
    return dict(tsys_k=float(pk / g - float(t_sky_ant_k)),
                gain_mw_per_k=float(g), t_ant_sky_k=float(t_sky_ant_k))


def tsys_from_yfactor(p_on_dbm, p_off_dbm, t_cal_k: float,
                      t_ref_k: float = 0.0) -> float:
    """Y-factor 2 điểm khi KHÔNG có tải hấp thụ.

    Vật lý: P_off = g·(T_sys + T_ref)  (trời trống, T_ref mặc định 0)
            P_on  = P_off + g·T_cal     (bật noise diode)
    ⇒ Y = 1 + T_cal/(T_sys + T_ref) ⇒ T_sys = T_cal/(Y − 1) − T_ref

    `t_cal_k` là nhiệt độ VƯỢT TRỘI của diode = Tn − T_load (Appendix A).
    """
    y = float(dbm_to_mw(p_on_dbm) / dbm_to_mw(p_off_dbm))
    if y <= 1.0:
        raise ValueError(f"Y = {y:.3f} ≤ 1: nguồn chuẩn không sáng hơn nền")
    return float(float(t_cal_k) / (y - 1.0) - float(t_ref_k))


def sefd_jy(tsys_k: float, aeff_m2: float) -> float:
    """SEFD [Jy] = 2k·T_sys / A_eff."""
    return float(2.0 * K_B * float(tsys_k) / float(aeff_m2) * JY)


def solar_sfd_jy(ta_k: float, aeff_m2: float, eta_a: float = 1.0,
                 tau: float = 0.0, cable_loss_db: float = 0.0) -> float:
    """SFD từ T_A theo Appendix A: 2k·T_A·e^τ·10^(L/10)/(α·A_CE) [Jy]."""
    corr = math.exp(float(tau)) * 10 ** (float(cable_loss_db) / 10.0)
    return float(2.0 * K_B * float(ta_k) * corr
                 / (float(eta_a) * float(aeff_m2)) * JY)


# ============================================ 5) CẬP NHẬT HỒ SƠ TRẠM
def update_band_tsys(profile_path: str, band_id: str, tsys_k: float,
                     note: str = "") -> dict:
    """Ghi T_sys ĐO ĐƯỢC vào hồ sơ trạm (psr_site) → SEFD tự suy lại."""
    import psr_site
    prof = psr_site.load_profile(profile_path)
    band = prof.band(band_id)
    if band is None:
        raise ValueError(f"hồ sơ không có băng {band_id!r} "
                         f"(có: {[b.id for b in prof.bands]})")
    old = float(band.tsys_k)
    band.tsys_k = float(tsys_k)
    if note:
        band.note = note
    prof.save(profile_path)
    return dict(band=band_id, tsys_old_k=old, tsys_new_k=float(tsys_k),
                sefd_jy=float(band.sefd_jy(prof.telescope)),
                a_eff_m2=float(prof.telescope.a_eff_m2()))


# ================================================================ 6) BÁO CÁO
def analyse_all(line: str | None = None, continuum: str | None = None,
                scan: str | None = None, out_dir: str | None = None,
                drifts: bool = True) -> dict:
    res: dict = {}
    if line:
        d = read_line(line)
        res["line"] = dict(meta=d["meta"],
                           stats=spectrum_stats(d["freqs_hz"], d["power_dbm"]))
        res["_line_data"] = d
    if continuum:
        d = read_continuum(continuum)
        rows = {}
        for lab in d["labels"]:
            y = d["rx"][lab]
            if int(np.isfinite(y).sum()) < 3:
                continue
            if drifts:
                dt = detrend(d["t_s"], y)
                d["rx"][lab + "_det"] = dt["y"]
                rows[lab] = dict(mean_dbm=float(np.nanmean(y)),
                                 slope_db_per_min=dt["slope_db_per_min"],
                                 p2p_db=dt["p2p_db"], n=dt["n"])
                # ĐO TRÔI THEO ĐOẠN: tránh hồi quy qua bậc nhảy của NCU
                ds = drift_segments(d["t_s"], y)
                rows[lab]["slope_naive_db_per_min"] = ds["slope_naive"]
                rows[lab]["slope_best_db_per_min"] = ds["slope_best_db_per_min"]
                rows[lab]["n_segments"] = ds["n_segments"]
                rows[lab]["segment_note"] = ds["note"]
                rows[lab]["segments"] = [
                    dict(kind=s["kind"], n=s["n"], level_dbm=s["level_dbm"],
                         i0=s["i0"], i1=s["i1"], t0_s=s["t0"], t1_s=s["t1"])
                    for s in ds["segments"]]
            else:
                fin = y[np.isfinite(y)]
                rows[lab] = dict(mean_dbm=float(np.mean(fin)),
                                 slope_db_per_min=float("nan"),
                                 p2p_db=float(np.percentile(fin, 99)
                                              - np.percentile(fin, 1)),
                                 n=int(fin.size))
        dt_all = np.diff(d["t_s"][np.isfinite(d["t_s"])])
        res["continuum"] = dict(meta=d["meta"], n_rx=len(d["labels"]),
                                n_samples=int(np.isfinite(d["t_s"]).sum()),
                                cadence_s=float(np.median(dt_all)) if dt_all.size
                                else float("nan"), rx=rows)
        # Allan deviation trên đoạn NỀN TĨNH dài nhất (kiểm tra có tích phân
        # nội khung hay không — Bτ lý thuyết ~0,0014 dB, đo được ~6 dB)
        try:
            lab0 = next((l for l in d["labels"]
                         if "slope_best_db_per_min" in rows.get(l, {})), None)
            if lab0 is not None:
                segs = rows[lab0].get("segments") or []
                base = [s for s in segs if s["kind"] == "baseline"]
                if base:
                    sb = max(base, key=lambda s: s["n"])
                    yb = d["rx"][lab0][sb["i0"]:sb["i1"]]
                    tb = d["t_s"][sb["i0"]:sb["i1"]]
                    res["continuum"]["allan"] = allan_deviation(
                        yb, float(np.median(np.diff(tb))) if tb.size > 1 else 1.0)
                    res["continuum"]["baseline_segment"] = sb
        except Exception:                       # noqa: BLE001
            pass
        res["_cont_data"] = d
    if scan:
        d = read_scan(scan)
        fits, curves = [], []
        for i in range(len(d["groups"])):
            c = scan_curve(d, i)
            # Một nhóm raster có thể chứa nhiều hàng đảo chiều hoặc EL trôi;
            # không fit như một cross-scan 1-D và không claim HPBW.
            _xg, _yg = np.asarray(c["x"], float), np.asarray(c["y"], float)
            _valid = np.isfinite(_xg) & np.isfinite(_yg)
            _xv = _xg[_valid]
            _ev = np.asarray(c["el"], float)[_valid]
            _monotonic = (_xv.size >= 5 and
                          (np.all(np.diff(_xv) >= 0) or np.all(np.diff(_xv) <= 0)))
            _el_span = float(np.ptp(_ev)) if _ev.size else float("inf")
            if not _monotonic or _el_span > max(0.5, 1.5 * d["step_deg"]):
                fit = dict(ok=False, reason=(
                    "không phải pass quét 1-D đơn điệu (raster/đổi hàng hoặc "
                    f"EL trôi {_el_span:.2f}°); không suy ra HPBW"),
                    n_used=int(_valid.sum()))
            else:
                fit = fit_gaussian_scan(_xg, _yg)
            fit.update(group=i, axis=c["axis"], centre_azel=c["centre"],
                       n_points=int(np.asarray(c["y"]).size),
                       n_valid=int(np.isfinite(np.asarray(c["y"], float)).sum()))
            fits.append(fit)
            if fit.get("ok"):
                curves.append(c)
        ok = [f for f in fits if f.get("ok")]
        # CHỈ kết luận HPBW khi khớp đủ tin cậy: SNR ≥ 5 và ≥ 15 điểm trên búp
        rel = [f for f in ok if f["snr"] >= 5.0 and f["n_used"] >= 15]
        _nmiss = int(np.sum(~np.isfinite(d["power_dbm"])))
        res["scan"] = dict(meta=d["meta"], n_points=int(d["az_deg"].size),
                           n_groups=len(d["groups"]),
                           n_valid=int(np.isfinite(d["power_dbm"]).sum()),
                           n_zero_missing=_nmiss,
                           frac_zero_missing=float(_nmiss / max(d["az_deg"].size, 1)),
                           repaired_truncated_az=list(
                               d["meta"].get("repaired_truncated_az") or []),
                           step_deg=float(d["step_deg"]),
                           az_range=[float(np.nanmin(d["az_deg"])),
                                     float(np.nanmax(d["az_deg"]))],
                           el_range=[float(np.nanmin(d["el_deg"])),
                                     float(np.nanmax(d["el_deg"]))],
                           groups=fits, reliable=bool(rel),
                           best=(max(rel, key=lambda f: f["snr"]) if rel else None))
        res["_scan_data"] = d
        res["_scan_curves"] = curves
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
        try:
            _figures(res, out_dir)
        except Exception as exc:             # noqa: BLE001
            res["figure_error"] = repr(exc)
        with open(os.path.join(out_dir, "rtcs_report.json"), "w",
                  encoding="utf-8") as fh:
            json.dump(_jsonable(res), fh, ensure_ascii=False, indent=2)
        with open(os.path.join(out_dir, "rtcs_report.txt"), "w",
                  encoding="utf-8") as fh:
            fh.write(text_report(res))
    return res


def _jsonable(o):
    if isinstance(o, dict):
        return {k: _jsonable(v) for k, v in o.items() if not k.startswith("_")}
    if isinstance(o, (list, tuple)):
        return [_jsonable(v) for v in o]
    if isinstance(o, (np.floating, np.integer)):
        o = float(o)
    if isinstance(o, float) and (math.isnan(o) or math.isinf(o)):
        return None
    return o


def text_report(res: dict) -> str:
    L = ["PHÂN TÍCH DỮ LIỆU XUẤT RTCS (POAM RTP-37)", ""]
    if "line" in res:
        s, m = res["line"]["stats"], res["line"]["meta"]
        L += [f"[PHỔ] {s.get('n_bins', m.get('n_bins', 0))} điểm · "
              f"span {s['span_mhz']:.1f} MHz · "
              f"endpoint grid spacing span/(N−1) {s['df_khz']:.3f} kHz"]
        if s.get("note_df"):
            L.append(f"      Ghi chú spacing: {s['note_df']}")
        L += [f"      trung vị {s['median_dbm']:.1f} dBm · "
              f"RMS {s['rms_db']:.2f} dB · "
              f"đỉnh {s['peak_hz']/1e6:.4f} MHz = {s['peak_dbm']:.1f} dBm "
              f"({s['peak_snr_db']:+.1f}σ)",
              f"      tâm đo {m.get('centre_hz_meas', 0)/1e9:.6f} GHz"]
        dc = s.get("dc_leak")
        if dc:
            L.append(f"      ⚠ Peak bất thường gần tâm phổ (ứng viên center artifact): "
                     f"bin {dc['bin']} (N={s['n_bins']}, f_c≈"
                     f"{dc['centre_hz']/1e9:.6f} GHz, lệch {dc['offset_hz']:.0f} Hz), "
                     f"{dc['delta_db']:+.2f} dB trên trung vị = {dc['sigma']:.1f}σ.")
            L.append("        Bin giữa có thể phù hợp DC/LO leak nhưng chưa xác định nguồn; "
                     "kiểm bằng tải và đổi LO/tâm tuning.")
        if m.get("iq_rate_sps"):
            L.append(f"      header: IQ {m['iq_rate_sps']/1e6:g} MS/s · "
                     f"BW {m.get('bandwidth_hz', 0)/1e6:g} MHz · "
                     f"gain {m.get('gain_db')} dB")
        if s.get("df_khz_median"):
            L.append(f"      (median(diff) ghi nhận = {s['df_khz_median']:.2f} kHz; "
                     "khác spacing từ span có thể do cột tần số làm tròn hoặc FFT-bin convention; "
                     "xác minh metadata receiver trước khi chọn số dùng)")
    if "continuum" in res:
        c = res["continuum"]
        L += ["", f"[CONTINUUM] {c['n_rx']} kênh · {c['n_samples']} mẫu · "
                  f"nhịp {c['cadence_s']:.2f} s"]
        for lab, v in c["rx"].items():
            sb = v.get("slope_best_db_per_min")
            if sb is not None and np.isfinite(sb) and v.get("n_segments", 0) > 1:
                L.append(f"      {lab}: TB {v['mean_dbm']:.1f} dBm · "
                         f"p2p {v['p2p_db']:.1f} dB · {v['n']} mẫu · "
                         f"{v['n_segments']} state theo mức công suất")
                L.append(f"        slope toàn chuỗi {v['slope_naive_db_per_min']:+.3f} "
                         f"dB/phút → baseline {sb:+.4f} dB/phút")
                if v.get("segment_note"):
                    L.append(f"        ⚠ {v['segment_note']}")
            else:
                L.append(f"      {lab}: TB {v['mean_dbm']:.1f} dBm · "
                         f"trôi {v['slope_db_per_min']:+.3f} dB/phút · "
                         f"p2p {v['p2p_db']:.1f} dB · {v['n']} mẫu")
        al = c.get("allan")
        if al:
            pts = " · ".join(f"{k}={v:.2f} dB" for k, v in al.items()
                              if k.startswith("tau_"))
            _bs = c.get("baseline_segment") or {}
            _nb = int(_bs.get("n", 0))
            L.append(f"      Allan σ trên đoạn nền {_nb} mẫu: {pts}")
            _s1 = float(al["sigma_single_sample_db"])
            _sch = float(al["expected_chi2_2_db"])
            L.append(f"      σ một mẫu đơn = {_s1:.2f} dB (lý thuyết χ²₂ chưa "
                     f"tích luỹ = {_sch:.2f} dB)")
            if al["sigma_single_sample_db"] > 0.7 * al["expected_chi2_2_db"]:
                L.append("      ⚠ độ lệch chuẩn gần mức của công suất mũ chưa "
                         "lấy trung bình. Đây là dấu hiệu cần kiểm tra, chưa đủ "
                         "để kết luận lỗi tích phân RTCS; xác minh bằng Load On.")
            if al.get("white_noise_slope_ok"):
                L.append("      σ_A giảm ≥ 2 lần theo τ → chưa chạm sàn 1/f, "
                         "tích luỹ dài còn có lợi.")
    if "scan" in res:
        s = res["scan"]
        L += ["", f"[SCAN] {s['n_points']} điểm · {s['n_groups']} nhóm QC "
                  f"(không xác định số lượt) · bước {s['step_deg']:.2f}° · AZ "
                  f"{s['az_range'][0]:.1f}–{s['az_range'][1]:.1f}° · EL "
                  f"{s['el_range'][0]:.1f}–{s['el_range'][1]:.1f}°"]
        if s.get("frac_zero_missing"):
            L.append(f"      mẫu 0.00 (mất dữ liệu) = "
                     f"{s['n_zero_missing']}/{s['n_points']} "
                     f"({100 * s['frac_zero_missing']:.1f} %) → đã đổi thành NaN")
        if s.get("truncated_az_rows"):
            for row in s["truncated_az_rows"]:
                L.append(f"      ⚠ dòng {row['index']} có AZ suffix '{row['suffix']}' bị cụt; "
                         "không tự khôi phục vì thiếu chữ số gốc")
        L.append(f"      Lưu ý: file không có timestamp từng điểm/scan-state; "
                 f"{s['n_groups']} group là discontinuity QC, không khẳng định "
                 "số pass quét.")
        for g in s["groups"]:
            _lost = g["n_points"] - g["n_valid"]
            if g.get("ok"):
                L.append(f"      nhóm QC {g['group']} ({g['axis']}): HPBW fit "
                         f"{g['hpbw_deg']:.2f}° · tâm {g['mu']:.2f}° · "
                         f"biên độ {g['amp_db']:.1f} dB · SNR {g['snr']:.0f} · "
                         f"nền {g['baseline_slope_db_per_deg']:+.3f} dB/° · "
                         f"{g['n_used']} điểm")
            else:
                L.append(f"      nhóm QC {g['group']} ({g['axis']}, AZ "
                         f"{g['centre_azel'][0]:.1f}°/EL {g['centre_azel'][1]:.1f}°): "
                         f"không khớp ({g.get('reason')}) — {g['n_valid']} "
                         f"/{g['n_points']} điểm hợp lệ"
                         + (f", mất {g['n_points'] - g['n_valid']} điểm 0.00"
                            if _lost else ""))
        if s.get("best"):
            b = s["best"]
            L.append(f"      → HPBW fit được = {b['hpbw_deg']:.2f}° "
                     f"(σ = {b['sigma_deg']:.2f}°) từ group {b['group']} (QC)")
        elif s.get("groups"):
            _msg = ("      → CHƯA KẾT LUẬN HPBW: cần cross-scan 1-D đơn điệu, EL gần "
                    "cố định, đủ mẫu/SNR. Group hiện tại có thể chứa nhiều hàng raster.")
            L.append(_msg)
            L.append("        Cần quét THẲNG qua nguồn: giữ nguyên EL, "
                     "quét AZ bước 0,2–0,5°, đủ ±3×HPBW hai bên.")
    if res.get("figure_error"):
        L += ["", f"(không vẽ được hình: {res['figure_error']})"]
    return "\n".join(L) + "\n"


def _figures(res: dict, out_dir: str) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    try:
        import psr_plots as PP
        place = PP.place_legend
    except Exception:                        # noqa: BLE001
        place = lambda ax: ax.legend(loc="best", fontsize=8)   # noqa: E731

    if "_line_data" in res:
        d, st = res["_line_data"], res["line"]["stats"]
        f, ax = plt.subplots(figsize=(8.4, 3.2))
        ax.plot(d["freqs_hz"] / 1e6, d["power_dbm"], lw=0.6, label="phổ đo")
        ax.axhline(st["median_dbm"], color="tab:orange", lw=1,
                   label=f"nền {st['median_dbm']:.1f} dBm")
        ax.plot([st["peak_hz"] / 1e6], [st["peak_dbm"]], "v", color="tab:red",
                label=f"đỉnh {st['peak_hz']/1e6:.4f} MHz")
        ax.set_xlabel("tần số (MHz)")
        ax.set_ylabel("công suất (dBm)")
        ax.set_title("RTCS — phổ Line observation")
        place(ax)
        f.tight_layout()
        f.savefig(os.path.join(out_dir, "rtcs_line.png"), dpi=120)
        plt.close(f)

    if "_cont_data" in res:
        d = res["_cont_data"]
        f, ax = plt.subplots(figsize=(8.4, 3.0))
        for lab in d["labels"][:3]:
            y = d["rx"].get(lab + "_det")
            if y is not None:
                ax.plot(d["t_s"], y, lw=0.7, label=f"{lab} (đã khử trôi)")
        ax.set_xlabel("thời gian (s)")
        ax.set_ylabel("công suất (dBm, đã bù trôi)")
        ax.set_title("RTCS — continuum, khử trôi tuyến tính")
        place(ax)
        f.tight_layout()
        f.savefig(os.path.join(out_dir, "rtcs_continuum.png"), dpi=120)
        plt.close(f)

    if res.get("_scan_curves"):
        c = res["_scan_curves"][0]
        fit = next((g for g in res["scan"]["groups"] if g.get("ok")), None)
        f, ax = plt.subplots(figsize=(8.4, 3.2))
        ax.plot(c["x"], c["y"], "o", ms=3, label="điểm quét")
        if fit:
            xs = np.linspace(float(np.nanmin(c["x"])), float(np.nanmax(c["x"])), 400)
            ax.plot(xs, _gauss(xs, fit["amp_db"], fit["mu"], fit["sigma_deg"],
                               fit["baseline_db"],
                               fit["baseline_slope_db_per_deg"]),
                    color="tab:red", lw=1.4,
                    label=f"Gauss: HPBW {fit['hpbw_deg']:.2f}°")
        ax.set_xlabel(f"{c['axis'].upper()} (°)")
        ax.set_ylabel("công suất (dBm)")
        ax.set_title("RTCS — quét ngang nguồn: khớp Gauss + nền tuyến tính")
        place(ax)
        f.tight_layout()
        f.savefig(os.path.join(out_dir, "rtcs_scan.png"), dpi=120)
        plt.close(f)


# =============================================================== 7) SELFTEST
def selftest() -> int:
    """Tự kiểm bằng dữ liệu TỔNG HỢP đã biết trước đáp số."""
    ok = n = 0

    def chk(name, cond, detail=""):
        nonlocal ok, n
        n += 1
        ok += bool(cond)
        print(f"  [{'PASS' if cond else 'FAIL'}] {name}"
              + (f" — {detail}" if detail else ""))

    rng = np.random.default_rng(7)

    tn = tn_from_enr(35.0, 70.0)
    chk("Appendix A: Tn(ENR=70 °C, Tamb=35 °C) = 344,6 K", abs(tn - 344.6) < 0.2,
        f"{tn:.1f} K")

    tsys_true, ta_true, tl, g = 150.0, 800.0, 300.0, 0.004
    p_load, p_sky = 0.01, 0.004 * (150.0 + 10.0)
    p_sun = 0.004 * (150.0 + 10.0 + 800.0)
    p_n = p_load + 0.004 * (tn - tl)
    d4 = four_point_ta(*(10 * np.log10(v) for v in (p_sun, p_sky, p_n, p_load)),
                       tn, tl)
    chk("4 điểm: T_A Mặt Trời đúng 800 K (≤ 1 %)", abs(d4["ta_k"] - ta_true) / ta_true < 0.01,
        f"{d4['ta_k']:.1f} K")
    dts = tsys_from_points(10 * np.log10(p_sky), 10 * np.log10(p_n),
                           10 * np.log10(p_load), tn, tl, 10.0)
    chk("4 điểm: T_sys đúng 150 K (≤ 1 %)", abs(dts["tsys_k"] - tsys_true) / tsys_true < 0.01,
        f"{dts['tsys_k']:.1f} K")
    chk("SEFD(150 K, A_eff 5,91 m²) ≈ 70,1 kJy", abs(sefd_jy(150.0, 5.91) / 1e3 - 70.06) < 0.5,
        f"{sefd_jy(150.0, 5.91)/1e3:.2f} kJy")
    chk("SFD Mặt Trời trong 10³–10⁶ Jy", 1e3 < solar_sfd_jy(ta_true, 5.91) < 1e6,
        f"{solar_sfd_jy(ta_true, 5.91):.0f} Jy")
    # Y-factor 2 điểm: OFF = trời trống (T_sys + 10 K), ON = OFF + diode
    t_ref, t_cal = 10.0, tn - tl
    p_off = 0.004 * (tsys_true + t_ref)
    p_on = p_off + 0.004 * t_cal
    yf = tsys_from_yfactor(10 * np.log10(p_on), 10 * np.log10(p_off),
                           t_cal, t_ref)
    chk("Y-factor 2 điểm cho cùng T_sys (≤ 2 %)",
        abs(yf - tsys_true) / tsys_true < 0.02, f"{yf:.1f} K")

    az = np.linspace(100, 160, 61)
    sig = 2.0
    pw = (-90 + 40 * np.exp(-0.5 * ((az - 131.3) / sig) ** 2)
          + 0.03 * (az - 130) + rng.normal(0, 0.25, az.size))
    fit = fit_gaussian_scan(az, pw)
    chk("Gauss: HPBW đúng 4,71° (≤ 5 %)",
        fit["ok"] and abs(fit["hpbw_deg"] - FWHM_PER_SIGMA * sig) / (FWHM_PER_SIGMA * sig) < 0.05,
        f"{fit.get('hpbw_deg', 0):.2f}°")
    chk("Gauss: tâm búp đúng 131,3° (≤ 0,3°)",
        fit["ok"] and abs(fit["mu"] - 131.3) < 0.3, f"{fit.get('mu', 0):.2f}°")
    chk("Gauss: nền nghiêng đúng 0,03 dB/° (≤ 30 %)",
        fit["ok"] and abs(fit["baseline_slope_db_per_deg"] - 0.03) < 0.009,
        f"{fit.get('baseline_slope_db_per_deg', 0):+.4f} dB/°")

    import tempfile
    with tempfile.TemporaryDirectory() as td:
        t = np.arange(0, 300, 1.0)
        yy = -80 - 1.9 / 60.0 * t + rng.normal(0, 0.1, t.size)
        yy[[10, 11, 12]] = 0.0
        pc = os.path.join(td, "continuum observation.txt")
        with open(pc, "w", encoding="utf-8") as fh:
            fh.write("Time - RTRS 1\tdBm - RTRS 1\tTime - RTRS 2\tdBm - RTRS 2\t\n")
            for i, v in enumerate(yy):
                fh.write(f"{t[i]:.0f}\t{v:.3f}\t{t[i]:.0f}\t0\t\n")
        dc = read_continuum(pc)
        chk("continuum: 0.0 → NaN (3 mẫu rỗng)",
            int(np.isnan(dc["rx"]["RTRS 1"]).sum()) == 3,
            f"{int(np.isnan(dc['rx']['RTRS 1']).sum())} mẫu")
        dt = detrend(dc["t_s"], dc["rx"]["RTRS 1"])
        chk("continuum: khử trôi đúng −1,9 dB/phút (≤ 5 %)",
            abs(dt["slope_db_per_min"] + 1.9) < 0.095,
            f"{dt['slope_db_per_min']:+.3f} dB/phút")
        chk("continuum: p2p sau khử trôi < 1,5 dB", dt["p2p_db"] < 1.5,
            f"{dt['p2p_db']:.2f} dB")

        f0 = 1.5e9
        fr = f0 + (np.arange(2048) - 1024) * 20e3
        sp = -100 + rng.normal(0, 1.0, fr.size)
        sp[1024] += 15.0
        pl = os.path.join(td, "line.csv")
        with open(pl, "w", encoding="utf-8") as fh:
            fh.write("Frequency /MHz - Plot 0\tPower /dBm - Plot 0\t\n")
            for a, b in zip(fr, sp):
                fh.write(f"{a:.6E}\t{b:.3f}\t\n")
        dl = read_line(pl)
        st = spectrum_stats(dl["freqs_hz"], dl["power_dbm"])
        chk("phổ fixture FFT 20 kHz/bin: 2048 điểm giữ grid spacing 20 kHz",
            dl["meta"]["n_bins"] == 2048 and abs(dl["meta"]["df_hz"] / 1e3 - 20) < 0.1,
            f"{dl['meta']['n_bins']} điểm · {dl['meta']['df_hz']/1e3:.1f} kHz")
        chk("phổ: đỉnh đúng 1500 MHz (≤ 1 bin)",
            abs(st["peak_hz"] - f0) <= dl["meta"]["df_hz"] * 1.01,
            f"{st['peak_hz']/1e6:.4f} MHz · {st['peak_snr_db']:+.1f}σ")

        # (1) Endpoint-inclusive 50 MHz/2048 grid gives 20 kHz/bin. A separate
        # fixture below tests the alternate span/(N−1) spacing convention and
        # rounded-column mismatch; do not assume it is universal for every RTCS file.
        fr1 = 1.5e9 - 25e6 + np.arange(2048) * (50e6 / 2047)
        # Rounded endpoint values can make adjacent-difference median differ.
        fr2 = np.array([float(f"{x:.5E}") for x in fr1])   # LabVIEW-style
        sp2 = -100 + rng.normal(0, 1.0, fr2.size)
        st2 = spectrum_stats(fr2, sp2)
        chk("phổ: endpoint grid spacing tính từ span/(N−1)",
            abs(st2["df_khz"] - 50_000 / 2047) < 0.01,
            f"{st2['df_khz']:.3f} kHz")
        chk("phổ: adjacent median giữ riêng để so metadata", st2["df_khz_median"] > 0,
            f"{st2['df_khz_median']:.3f} kHz")

        # (2) Center-bin peak is a candidate artifact, not proven DC/LO.
        sp3 = -100 + rng.normal(0, 1.0, 2048)
        sp3[1023] += 13.0
        st3 = spectrum_stats(fr, sp3)
        chk("phổ: center peak candidate được gắn cờ, không kết luận nguồn",
            st3.get("dc_leak") is not None
            and st3["dc_leak"]["bin"] in (1022, 1023, 1024, 1025),
            str(st3.get("dc_leak"))[:60])
        sp5 = -100 + rng.normal(0, 1.0, 2048)
        sp5[1025] += 13.0
        st5 = spectrum_stats(fr, sp5)
        chk("phổ: candidate chấp nhận bin giữa lân cận theo quy ước FFT",
            st5.get("dc_leak") is not None and st5["dc_leak"]["bin"] == 1025,
            str(st5.get("dc_leak"))[:50])
        # đỉnh ở RÌA (không phải tâm) thì KHÔNG được gọi là rò DC
        sp4 = -100 + rng.normal(0, 1.0, 2048)
        sp4[300] += 25.0
        st4 = spectrum_stats(fr, sp4)
        chk("phổ: đỉnh ngoài tâm → không gắn cờ DC",
            st4.get("dc_leak") is None, f"peak bin 300 · {st4['peak_snr_db']:+.1f}σ")

        # (3) ĐỘ TRÔI: không được hồi quy qua bậc nhảy của khối hiệu chuẩn NCU
        tseg = np.arange(1000, dtype=float)
        yseg = -88.0 + 0.002 * tseg / 60.0 + rng.normal(0, 6.0, 1000)
        for i0, i1 in ((100, 160), (200, 320), (400, 480)):   # 3 bậc NCU +30 dB
            yseg[i0:i1] += 30.0
        naive = detrend(tseg, yseg)["slope_db_per_min"]
        ds3 = drift_segments(tseg, yseg)
        chk("continuum: tách được các đoạn (bậc NCU vs nền)",
            ds3["n_segments"] >= 4, f"{ds3['n_segments']} đoạn")
        # sai số thống kê của độ dốc trên đoạn ~500 mẫu σ=6 dB ≈ 0,11 dB/phút
        # σ_slope(/s) = σ/(√N·σ_t); đổi sang /phút → ×60
        _sig_sl = 6.0 / (np.sqrt(500) * float(np.std(tseg[500:]))) * 60.0
        chk("continuum: trôi đoạn nền ≤ 3σ thống kê (hết âm giả tạo)",
            abs(ds3["slope_best_db_per_min"]) <= 3 * _sig_sl
            and abs(naive) > 3 * abs(ds3["slope_best_db_per_min"]),
            f"naive {naive:+.3f} → nền {ds3['slope_best_db_per_min']:+.4f} "
            f"dB/phút (3σ = {3 * _sig_sl:.3f})")
        chk("continuum: note tách slope toàn chuỗi với baseline, không gán nguồn",
            bool(ds3["note"]) and "bước" in ds3["note"], ds3["note"][:56])
        al3 = allan_deviation(yseg[500:1000], 1.0)
        chk("continuum: Allan σ giảm theo τ (nhiễu trắng, chưa chạm 1/f)",
            al3["white_noise_slope_ok"],
            " · ".join(f"{k}={v:.2f}" for k, v in al3.items()
                       if k.startswith("tau_")))
        chk("continuum: Allan σ một mẫu ≈ 5,57 dB (χ²₂ chưa tích luỹ)",
            abs(al3["sigma_single_sample_db"] - 5.57) < 1.5,
            f"{al3['sigma_single_sample_db']:.2f} dB")

        ps = os.path.join(td, "scan.txt")
        with open(ps, "w", encoding="utf-8") as fh:
            fh.write('RTRS: "RTRS1", IQ Rate=10000000.000000, Samples=2048, '
                     'Carrier Freq.=1500000000.000000, Gain=20, '
                     'Bandwidth=50000000.000000\n')
            fh.write("AZ-deg\tEL-deg\tRTRS1\n")
            for a, b in zip(az, pw):
                fh.write(f"{a:.2f}\t45.00\t{b:.2f}\n")
            fh.write("190.00\t45.00\t0.00\n")
        ds = read_scan(ps)
        chk("scan: bóc header (IQ 10 MS/s, BW 50 MHz)",
            ds["meta"].get("iq_rate_sps") == 1e7
            and ds["meta"].get("bandwidth_hz") == 5e7,
            f"{ds['meta'].get('iq_rate_sps')} · {ds['meta'].get('bandwidth_hz')}")
        chk("scan: mẫu 0.00 → NaN", int(np.isnan(ds["power_dbm"]).sum()) == 1)

        # (4) DÒNG ĐẦU BỊ CẮT SỐ ("183.55" → ".55") + discontinuity split
        pt = os.path.join(td, "scan_cut.txt")
        with open(pt, "w", encoding="utf-8") as fh:
            fh.write('RTRS: "RTRS1", IQ Rate=10000000.000000, Samples=2048, '
                     'Carrier Freq.=1500000000.000000, Gain=20, '
                     'Bandwidth=50000000.000000\n')
            fh.write("AZ-deg\tEL-deg\tRTRS1\n")
            fh.write(".55\t57.15\t-86.00\n")          # 183.55 bị cắt
            for k in range(1, 12):
                fh.write(f"{183.55 + 0.51 * k:.2f}\t57.15\t-86.00\n")
            for k in range(12, 22):                    # nhảy sang cụm khác
                fh.write(f"{225.0 + 0.51 * (k - 12):.2f}\t42.60\t-60.00\n")
            fh.write("230.10\t42.60\t0.00\n")
        dt2 = read_scan(pt)
        rep = dt2["meta"].get("repaired_truncated_az") or []
        chk("scan: suffix AZ bị cụt được gắn cờ, không nội suy toạ độ",
            dt2["meta"].get("n_truncated_az") == 1
            and np.isnan(dt2["az_deg"][0])
            and not dt2["meta"].get("repaired_truncated_az"),
            str(dt2["meta"].get("truncated_az_rows")))
        chk("scan: min AZ dùng các điểm có dữ liệu; suffix vẫn missing",
            float(np.nanmin(dt2["az_deg"])) > 100.0 and np.isnan(dt2["az_deg"][0]),
            f"min={np.nanmin(dt2['az_deg']):.2f}°, first=NaN")
        chk("scan: tách đúng 2 đoạn discontinuity trong fixture",
            len(dt2["groups"]) == 2, f"{len(dt2['groups'])} đoạn")
        chk("scan: thống kê mẫu 0.00 mất dữ liệu",
            dt2["meta"].get("n_zero_samples") == 1
            and 0.0 < dt2["meta"].get("frac_zero", 0) < 0.2,
            f"{dt2['meta'].get('n_zero_samples')} · "
            f"{dt2['meta'].get('frac_zero', 0) * 100:.1f} %")
        # Truncated AZ suffix is missing, not fabricated from the next value.
        chk("scan: .55 suffix recorded as truncated and AZ stays NaN",
            dt2["meta"].get("n_truncated_az") == 1
            and np.isnan(dt2["az_deg"][0])
            and not dt2["meta"].get("repaired_truncated_az"),
            str(dt2["meta"].get("truncated_az_rows")))
        chk("scan: step estimate remains about 0.51°",
            abs(dt2["step_deg"] - 0.51) < 0.05, f"{dt2['step_deg']:.3f}°")
        # A deliberately reversed AZ track is not a one-dimensional cross-scan.
        pr = os.path.join(td, "raster.txt")
        with open(pr, "w", encoding="utf-8") as fh:
            fh.write("AZ-deg\tEL-deg\tRTRS1\n")
            for aa in list(np.linspace(10, 15, 8)) + list(np.linspace(15, 10, 8)):
                fh.write(f"{aa:.2f}\t45.00\t-80.0\n")
        dr = read_scan(pr)
        cr = scan_curve(dr, 0)
        _mono = np.all(np.diff(cr["x"]) >= 0) or np.all(np.diff(cr["x"]) <= 0)
        chk("scan: raster reversal recognized as nonmonotonic, not cross-scan",
            not _mono, f"AZ direction reverses in {len(dr['az_deg'])} points")

    print(f"\n{ok}/{n} kiểm tra PASS")
    return 0 if ok == n else 1


# ====================================================================== CLI
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Đọc & phân tích dữ liệu xuất của RTCS (POAM RTP-37)")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--line", help="line.csv hoặc 'Line observation.txt'")
    ap.add_argument("--continuum", help="continuum observation.txt/.csv")
    ap.add_argument("--scan", help="log quét (vd 123.txt)")
    ap.add_argument("--out", help="thư mục kết quả")
    ap.add_argument("--no-detrend", action="store_true")
    ap.add_argument("--profile", help="hồ sơ trạm (psr_site) để ghi T_sys")
    ap.add_argument("--band", default="lband", help="mã băng trong hồ sơ")
    ap.add_argument("--tsys", type=float, help="T_sys (K) đo được để ghi hồ sơ")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if not any((a.line, a.continuum, a.scan)):
        ap.print_help()
        return 2
    import datetime
    out = a.out or os.path.join(
        "results", datetime.datetime.now().strftime("%Y%m%d_%H%M%S"), "rtcs")
    res = analyse_all(a.line, a.continuum, a.scan, out, not a.no_detrend)
    print(text_report(res))
    print(f"→ {out}")
    if a.tsys and a.profile:
        print("→ hồ sơ:", update_band_tsys(a.profile, a.band, a.tsys,
                                          note=f"T_sys RTCS {datetime.date.today()}"))
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                        # noqa: BLE001
        pass
    sys.exit(main())
