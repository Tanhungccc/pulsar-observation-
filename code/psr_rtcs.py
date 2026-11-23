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
        c = [x for x in re.split(r"[\t;,]", ln) if x.strip() != ""]
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
    meta["df_hz"] = float(np.median(np.diff(f))) if f.size > 1 else 0.0
    meta["span_hz"] = float(f.max() - f.min()) if f.size > 1 else 0.0
    meta["centre_hz_meas"] = float(0.5 * (f.max() + f.min()))
    return dict(freqs_hz=f, power_dbm=p, meta=meta)


def spectrum_stats(f, p) -> dict:
    """Nền (trung vị), RMS bền vững, đỉnh nổi bật nhất theo σ."""
    med = float(np.median(p))
    rms = 1.4826 * float(np.median(np.abs(p - med))) or 1e-9
    k = int(np.argmax(p))
    return dict(median_dbm=med, rms_db=rms, peak_dbm=float(p[k]),
                peak_hz=float(f[k]), peak_snr_db=float((p[k] - med) / rms),
                span_mhz=float((f.max() - f.min()) / 1e6),
                df_khz=float(np.median(np.diff(f)) / 1e3) if f.size > 1 else 0.0)


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
        c = [x.strip() for x in re.split(r"[\t;,]", ln)]
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
def read_scan(path: str) -> dict:
    """Đọc log quét → {az_deg, el_deg, power_dbm, meta, groups}."""
    raw = open(path, encoding="utf-8", errors="replace").read()
    meta = _meta_from_text(raw)
    az, el, pw = [], [], []
    started = False
    for ln in raw.splitlines():
        c = [x for x in re.split(r"[\t;,]", ln) if x.strip() != ""]
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
        az.append(a)
        el.append(e)
        pw.append(np.nan if (p is None or p == 0.0) else p)
    if not az:
        raise ValueError(f"{os.path.basename(path)}: không thấy dòng AZ/EL/power")
    a, e, p = (np.asarray(az, float), np.asarray(el, float),
               np.asarray(pw, float))
    # tách lượt quét: AZ nhảy lớn so với bước quét thường
    d = np.abs(np.diff(a))
    step = float(np.median(d[d > 0])) if np.any(d > 0) else 1.0
    cuts = np.where(d > max(5.0 * step, 2.0))[0] + 1
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
        res["_cont_data"] = d
    if scan:
        d = read_scan(scan)
        fits, curves = [], []
        for i in range(len(d["groups"])):
            c = scan_curve(d, i)
            fit = fit_gaussian_scan(c["x"], c["y"])
            fit.update(group=i, axis=c["axis"], centre_azel=c["centre"])
            fits.append(fit)
            if fit.get("ok"):
                curves.append(c)
        ok = [f for f in fits if f.get("ok")]
        # CHỈ kết luận HPBW khi khớp đủ tin cậy: SNR ≥ 5 và ≥ 15 điểm trên búp
        rel = [f for f in ok if f["snr"] >= 5.0 and f["n_used"] >= 15]
        res["scan"] = dict(meta=d["meta"], n_points=int(d["az_deg"].size),
                           n_groups=len(d["groups"]),
                           n_valid=int(np.isfinite(d["power_dbm"]).sum()),
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
        L += [f"[PHỔ] {m.get('n_bins', 0)} điểm · span {s['span_mhz']:.1f} MHz · "
              f"Δf {s['df_khz']:.2f} kHz",
              f"      trung vị {s['median_dbm']:.1f} dBm · RMS {s['rms_db']:.2f} dB · "
              f"đỉnh {s['peak_hz']/1e6:.4f} MHz = {s['peak_dbm']:.1f} dBm "
              f"({s['peak_snr_db']:+.1f}σ)",
              f"      tâm đo {m.get('centre_hz_meas', 0)/1e9:.6f} GHz"]
        if m.get("iq_rate_sps"):
            L.append(f"      header: IQ {m['iq_rate_sps']/1e6:g} MS/s · "
                     f"BW {m.get('bandwidth_hz', 0)/1e6:g} MHz · "
                     f"gain {m.get('gain_db')} dB")
    if "continuum" in res:
        c = res["continuum"]
        L += ["", f"[CONTINUUM] {c['n_rx']} kênh · {c['n_samples']} mẫu · "
                  f"nhịp {c['cadence_s']:.2f} s"]
        for lab, v in c["rx"].items():
            L.append(f"      {lab}: TB {v['mean_dbm']:.1f} dBm · "
                     f"trôi {v['slope_db_per_min']:+.3f} dB/phút · "
                     f"p2p {v['p2p_db']:.1f} dB · {v['n']} mẫu")
    if "scan" in res:
        s = res["scan"]
        L += ["", f"[SCAN] {s['n_points']} điểm · {s['n_groups']} lượt · "
                  f"bước {s['step_deg']:.2f}° · AZ "
                  f"{s['az_range'][0]:.1f}–{s['az_range'][1]:.1f}° · EL "
                  f"{s['el_range'][0]:.1f}–{s['el_range'][1]:.1f}°"]
        for g in s["groups"]:
            if g.get("ok"):
                L.append(f"      lượt {g['group']} ({g['axis']}): HPBW "
                         f"{g['hpbw_deg']:.2f}° · tâm {g['mu']:.2f}° · "
                         f"biên độ {g['amp_db']:.1f} dB · SNR {g['snr']:.0f} · "
                         f"nền {g['baseline_slope_db_per_deg']:+.3f} dB/° · "
                         f"{g['n_used']} điểm")
            else:
                L.append(f"      lượt {g['group']}: không khớp ({g.get('reason')})")
        if s.get("best"):
            b = s["best"]
            L.append(f"      → HPBW THỰC TẾ = {b['hpbw_deg']:.2f}° "
                     f"(σ = {b['sigma_deg']:.2f}°) từ lượt {b['group']}")
        elif any(g.get("ok") for g in s["groups"]):
            _msg = ("      → CHƯA KẾT LUẬN được HPBW: khớp yếu "
                    "(SNR < 5 hoặc < 15 điểm/búp).")
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
        chk("phổ: đọc 2048 điểm, Δf 20 kHz",
            dl["meta"]["n_bins"] == 2048 and abs(dl["meta"]["df_hz"] / 1e3 - 20) < 0.1,
            f"{dl['meta']['n_bins']} điểm · {dl['meta']['df_hz']/1e3:.1f} kHz")
        chk("phổ: đỉnh đúng 1500 MHz (≤ 1 bin)",
            abs(st["peak_hz"] - f0) <= dl["meta"]["df_hz"] * 1.01,
            f"{st['peak_hz']/1e6:.4f} MHz · {st['peak_snr_db']:+.1f}σ")

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
