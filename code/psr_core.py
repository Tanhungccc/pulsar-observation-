# -*- coding: utf-8 -*-
"""
psr_core.py — Lõi DSP cho quan sát pulsar bằng kính POAM RTP-3.7.

Chỉ phụ thuộc numpy. Mọi hàm nhận "dyn" (dynamic spectrum / waterfall) dạng
mảng 2 chiều (nchan, ntime) chứa CÔNG SUẤT (đã bình phương), không phải IQ.

Quy ước đơn vị:
    tần số  : MHz
    thời gian: giây  (tsamp tính bằng giây)
    DM      : pc cm^-3
    dyn     : đơn vị tuỳ ý (thường là "đếm ADC" hoặc K)

Các khối thuật toán (đánh số khớp với docs/01_vat_ly_va_thuat_toan.md):
    A2  khử tán sắc không kết hợp (incoherent dedispersion)
    A4  fold theo chu kỳ (epoch folding, có Pdot)
    A5  tìm chu kỳ bằng FFT + cộng hài
    A7  lọc khớp boxcar (single pulse / giant pulse)
    A9  khử RFI (zero-DM, spectral kurtosis, cắt kênh)
    A10 đo SNR / độ rộng xung
    A11 ước lượng DM bằng quét DM
"""
from __future__ import annotations

import sys

import numpy as np


def ensure_utf8_stdout() -> None:
    """Console Windows mặc định cp1252 → ép UTF-8 để in tiếng Việt."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


# Hằng số tán sắc: t[s] = K_DM * DM / nu[MHz]^2
K_DM = 4.148808e3
C_KMS = 299792.458
DAY_S = 86400.0


# ---------------------------------------------------------------- A: tán sắc
def dm_delay_s(dm: float, f_mhz, f_ref_mhz: float | None = None):
    """Độ trễ tán sắc (giây) tại tần số f so với f_ref (mặc định: vô cực)."""
    f = np.asarray(f_mhz, dtype=float)
    t = K_DM * float(dm) / f**2
    if f_ref_mhz is not None:
        t = t - K_DM * float(dm) / float(f_ref_mhz) ** 2
    return t


def band_smear_ms(dm: float, f_lo_mhz: float, f_hi_mhz: float) -> float:
    """Trải xung do tán sắc trên TOÀN dải (khi không khử tán sắc) — ms."""
    return abs(dm_delay_s(dm, f_lo_mhz, f_hi_mhz)) * 1e3


def chan_smear_ms(dm: float, f_mhz: float, chan_width_mhz: float) -> float:
    """Trải xung còn lại TRONG một kênh sau khử tán sắc không kết hợp — ms."""
    return abs(dm_delay_s(dm, f_mhz - chan_width_mhz / 2,
                          f_mhz + chan_width_mhz / 2)) * 1e3


def coherent_filter_taps(dm: float, freqs_mhz, n_fft: int, fs_hz: float):
    """A3 — bộ lọc khử tán sắc KẾT HỢP (coherent) trong miền tần số.

    Trả về hàm nhân phức H(f) để nhân với phổ của một block IQ dài n_fft mẫu.
    Chỉ dùng khi SDR cho phép đọc khối IQ liên tục (RTL-SDR: có, nhưng mất mẫu
    giữa các lần đọc → trong thực tế cần SDR có stream liên tục / file ghi thô).
    """
    f = np.asarray(freqs_mhz, dtype=float) * 1e6          # Hz
    f0 = f.mean()
    k = K_DM * float(dm) * 1e6                            # hằng số trong Hz
    phase = 2.0 * np.pi * k * (1.0 / f - 1.0 / f0) * (n_fft / fs_hz)
    # Lưu ý: hệ số (n_fft/fs) quy đổi "trễ nhóm" sang pha rời rạc của block.
    return np.exp(1j * phase)


# ------------------------------------------------------- B: số hoá / chia kênh
def channelize(iq, nchan: int, fs_hz: float, f_center_mhz: float | None = None):
    """A1/A2 — biến chuỗi IQ phức thành phổ công suất theo thời gian.

    Trả về (dyn, freqs_mhz) với dyn.shape == (nchan, ntime).
    Đây chính là việc mà GUI hiện tại làm bằng Welch/FFT trung bình.
    """
    iq = np.asarray(iq)
    nblk = len(iq) // nchan
    x = iq[: nblk * nchan].reshape(nblk, nchan)
    spec = np.fft.fftshift(np.fft.fft(x, axis=1), axes=1)
    dyn = (np.abs(spec) ** 2).T.astype(np.float32)
    freqs = np.fft.fftshift(np.fft.fftfreq(nchan, 1.0 / fs_hz)) / 1e6
    if f_center_mhz is not None:
        freqs = freqs + float(f_center_mhz)
    return dyn, freqs


# ----------------------------------------------------- C: khử tán sắc (A2)
def dedisperse(dyn, freqs_mhz, dm: float, tsamp_s: float,
               weights=None, f_ref_mhz: float | None = None):
    """A2 — khử tán sắc KHÔNG kết hợp bằng dịch nguyên mẫu từng kênh.

    Ý tưởng: kênh tần số thấp đến trễ hơn; ta cắt bỏ phần đầu của mỗi kênh
    đúng bằng (t_nu - t_fref) rồi cộng tất cả lại.

    Trả về (series, n_dropped) — series dài hơn 0, n_dropped mẫu bị bỏ ở đầu.
    """
    dyn = np.asarray(dyn, dtype=np.float64)
    freqs = np.asarray(freqs_mhz, dtype=float)
    if f_ref_mhz is None:
        f_ref_mhz = float(freqs.max())          # tham chiếu: kênh tần số cao
    delays = dm_delay_s(dm, freqs, f_ref_mhz)   # >= 0
    shifts = np.rint(delays / tsamp_s).astype(int)
    shifts = np.clip(shifts, 0, dyn.shape[1] - 1)
    smax = int(shifts.max())
    n = dyn.shape[1] - smax
    if n <= 0:
        raise ValueError("DM quá lớn so với độ dài dữ liệu (không còn mẫu)")
    out = np.zeros(n, dtype=np.float64)
    w = np.ones(len(freqs)) if weights is None else np.asarray(weights, float)
    for i, sh in enumerate(shifts):
        out += w[i] * dyn[i, sh:sh + n]
    out /= w.sum()
    return out, smax


def dedisperse_stack(dyn, freqs_mhz, tsamp_s: float, dm_grid,
                     period_s: float | None = None, nbins: int = 128):
    """Quét DM (A11): với mỗi DM, khử tán sắc rồi đo SNR (fold nếu biết P)."""
    snrs, profs = [], []
    for dm in np.atleast_1d(dm_grid):
        s, _ = dedisperse(dyn, freqs_mhz, dm, tsamp_s)
        if period_s is None:
            v = boxcar_snr(s, widths=(1, 2, 4, 8))[0]
            prof = None
        else:
            prof, _ = fold(s, tsamp_s, period_s, nbins=nbins)
            v = profile_snr(prof)[0]
        snrs.append(v)
        profs.append(prof)
    return np.asarray(snrs), profs


def dm_from_subbands(dyn, freqs_mhz, tsamp_s: float, period_s: float,
                     nsub: int = 4, nbins: int = 512):
    """A11b — ĐO DM bằng ĐỘ TRỄ GIỮA CÁC DẢI CON (dùng TRỌNG TÂM hồ sơ xung).

    Không cần biết DM trước: cắt dải thành nsub dải con, fold MỖI dải con theo
    chu kỳ đã biết, rồi đo độ trễ của xung giữa các dải con. Khớp tuyến tính

        t(nu) − t(nu_ref) = K_DM · DM · (1/nu² − 1/nu_ref²)

    Dùng TRỌNG TÂM (first moment) của phần xung dương thay vì đỉnh tương quan:
    tích chập với hạt nhân trải tán sắc GIỮ NGUYÊN trọng tâm, còn đỉnh tương
    quan thì bị lệch vài % → đây là lý do phương pháp này không bị thiên lệch.

    Điều kiện dùng: SNR mỗi dải con ≳ 10. Với SNR thấp hơn, hãy dùng quét DM
    (A11a) và chấp nhận sai số lớn.

    Trả về dict {dm, dm_err, lags_s, freqs_mhz, sub_profiles}.
    """
    dyn = np.asarray(dyn, dtype=np.float64)
    freqs = np.asarray(freqs_mhz, dtype=float)
    order = np.argsort(freqs)
    f, d = freqs[order], dyn[order]
    edges = np.linspace(0, len(f), nsub + 1).astype(int)
    bin_period = period_s / nbins

    profiles, fmean, cent = [], [], []
    for k in range(nsub):
        sl = slice(edges[k], edges[k + 1])
        prof, _ = fold(d[sl].mean(axis=0), tsamp_s, period_s, nbins=nbins)
        profiles.append(prof - np.median(prof))
        fmean.append(f[sl].mean())
        # định vị xung TRONG CHÍNH dải con đó (boxcar = lọc khớp, bền với SNR thấp)
        _, wk, phk = profile_snr(prof)
        wk = max(wk, 1)
        k0 = phk * nbins
        offs = np.arange(-int(1.6 * wk), int(1.6 * wk) + 1)
        y = np.clip(prof[(np.round(k0).astype(int) + offs) % nbins], 0.0, None)
        # pha tuyệt đối của trọng tâm = pha tâm boxcar + độ lệch trong cửa sổ
        cent.append(float(phk) * period_s
                    + float((y * offs).sum() / max(y.sum(), 1e-12)) * bin_period)
    cent = np.asarray(cent)                            # giây, pha tuyệt đối
    fmean = np.asarray(fmean)

    # tham chiếu: dải con TẦN SỐ CAO NHẤT (đến sớm nhất); bỏ cuộn vòng pha
    lag = (cent - cent[-1] + 0.5 * period_s) % period_s - 0.5 * period_s
    x = 1.0 / fmean**2 - 1.0 / fmean[-1]**2            # MHz^-2, >= 0
    A = np.vstack([x, np.ones_like(x)]).T
    sol, *_ = np.linalg.lstsq(A, lag, rcond=None)
    coef, offset = float(sol[0]), float(sol[1])
    dm = coef / K_DM
    resid = lag - A @ np.array([coef, offset])
    dm_err = float(np.sqrt(np.mean(resid**2)) / abs(coef) * abs(dm)
                   * np.sqrt(len(lag))) if abs(coef) > 0 else float("nan")
    # sai số hệ thống ~3% (cửa sổ trọng tâm + dạng xung) — đừng báo 0.1
    dm_err = max(dm_err, 0.03 * abs(dm))
    return {"dm": dm, "dm_err": dm_err, "lags_s": lag,
            "freqs_mhz": fmean, "sub_profiles": np.array(profiles)}


# ---------------------------------------------------------------- D: fold (A4)
def fold(series, tsamp_s: float, period_s: float, nbins: int = 256,
         pdot: float = 0.0, t0_s: float = 0.0, weights=None):
    """A4 — epoch folding có hiệu chỉnh Pdot bậc 1.

    phase(t) = (t - t0)/P - 0.5 * Pdot * (t - t0)^2 / P^2
    Trả về (profile, counts) — profile là giá trị trung bình mỗi bin.
    """
    x = np.asarray(series, dtype=np.float64)
    n = len(x)
    t = np.arange(n, dtype=np.float64) * tsamp_s
    dt = t - float(t0_s)
    ph = dt / period_s - 0.5 * pdot * dt**2 / period_s**2
    idx = np.floor(np.mod(ph, 1.0) * nbins).astype(np.int64)
    idx[idx >= nbins] = nbins - 1
    w = np.ones(n) if weights is None else np.asarray(weights, float)
    num = np.bincount(idx, weights=x * w, minlength=nbins)
    den = np.bincount(idx, weights=w, minlength=nbins)
    prof = num / np.maximum(den, 1e-12)
    return prof, den


def fold_search_period(series, tsamp_s: float, period_grid, nbins: int = 128):
    """Fold thử nhiều chu kỳ (khi chưa biết P chính xác) → SNR tốt nhất."""
    best = (-1e9, None, None)
    for p in np.atleast_1d(period_grid):
        prof, _ = fold(series, tsamp_s, p, nbins=nbins)
        s = profile_snr(prof)[0]
        if s > best[0]:
            best = (s, p, prof)
    return best


def refine_period(series, tsamp_s: float, period0: float,
                  t_obs_s: float | None = None, nbins: int = 256,
                  iters: int = 3, nstep: int = 33):
    """A4b — TINH CHỈNH CHU KỲ bằng quét thu hẹp nhiều tầng (zoom search).

    Vì sao bắt buộc: độ phân giải tần số của FFT là 1/T_obs, tương ứng sai số
    chu kỳ ΔP/P ≈ P/T_obs. Với P = 0.71 s và T_obs = 90 s → ΔP ≈ 6e-3·P, tức
    0.4%: tích pha trôi ~0.34 chu kỳ trong 90 s → hồ sơ bị nhoè HOÀN TOÀN.
    (Đây là lỗi phổ biến nhất khi tự viết pipeline fold.)

    Cách làm: quét f trong ±1/T với bước đủ mịn để trôi pha < 1/W mỗi vòng,
    lặp lại quanh đỉnh với biên độ giảm dần (bracket → zoom → zoom).

    Trả về (period_best, snr_best, profile).
    """
    x = np.asarray(series, dtype=np.float64)
    if t_obs_s is None:
        t_obs_s = len(x) * tsamp_s
    f0 = 1.0 / period0
    dspan = 1.0 / t_obs_s                      # độ rộng 1 bin FFT
    best_p, best_s, best_prof = period0, -1e9, None
    for it in range(iters):
        grid = f0 + np.linspace(-dspan, dspan, nstep)
        for f in grid:
            p = 1.0 / f
            prof, _ = fold(x, tsamp_s, p, nbins=nbins)
            s = profile_snr(prof)[0]
            if s > best_s:
                best_s, best_p, best_prof = s, p, prof
        f0 = 1.0 / best_p
        dspan /= nstep / 2.0                   # thu hẹp quanh đỉnh
    return best_p, best_s, best_prof


# ------------------------------------------------------------- E: SNR (A10)
def profile_snr(prof, widths=(1, 2, 3, 4, 6, 8, 12, 16, 24, 32)):
    """A10 — SNR của hồ sơ xung bằng lọc khớp boxcar tối ưu trên mọi độ rộng.

    Cửa sổ là VÒNG (circular): xung có thể nằm vắt qua pha 0..1. Nếu dùng
    cumsum thẳng, xung ở biên bị chia đôi và SNR tụt ~2 lần — lỗi rất dễ mắc.

    Trả về (snr, width_bins, phase_peak).
    """
    p = np.asarray(prof, dtype=float)
    med = np.median(p)
    rms = 1.4826 * np.median(np.abs(p - med)) + 1e-12
    d = p - med
    n = len(p)
    c = np.concatenate(([0.0], np.cumsum(np.concatenate((d, d)))))
    best = (0.0, 0, 0.0)
    for w in widths:
        if w > n:
            continue
        s = c[w:w + n] - c[0:n]              # tổng w bin liên tiếp, vòng
        z = s / (rms * np.sqrt(w))
        k = int(np.argmax(z))
        if z[k] > best[0]:
            ph = ((k + (w - 1) / 2.0) / n) % 1.0
            best = (float(z[k]), int(w), float(ph))
    return best


def boxcar_snr(series, widths=(1, 2, 3, 4, 6, 8, 16, 32, 64), stride: int = 1):
    """A7 — tìm xung ĐƠN bằng lọc khớp boxcar trên chuỗi thời gian.

    Trả về (snr_max, width, index) — dùng cho giant pulse / single pulse.
    """
    x = np.asarray(series, dtype=float)
    x = x[::stride] if stride > 1 else x
    med = np.median(x)
    rms = 1.4826 * np.median(np.abs(x - med)) + 1e-12
    d = x - med
    c = np.concatenate(([0.0], np.cumsum(d)))
    best = (0.0, 0, 0)
    for w in widths:
        if w > len(d):
            continue
        s = c[w:] - c[:-w]
        z = s / (rms * np.sqrt(w))
        k = int(np.argmax(z))
        if z[k] > best[0]:
            best = (float(z[k]), int(w), int((k + (w - 1) / 2) * stride))
    return best


# ----------------------------------------------------- F: tìm chu kỳ FFT (A5)
def fft_search(series, tsamp_s: float, fmin_hz: float = 0.1,
               fmax_hz: float | None = None, nharm: int = 4, top: int = 10):
    """A5 — FFT + cộng hài (harmonic summing), kiểu "power spectrum" của PRESTO.

    Trả về danh sách dict {freq_hz, period_s, power_ratio, harmonics}.
    power_ratio = công suất đỉnh / trung vị công suất trong dải (thô, chưa
    hiệu chỉnh số lần thử — dùng để xếp hạng, không phải p-value).
    """
    x = np.asarray(series, dtype=np.float64)
    n = len(x)
    x = x - x.mean()
    fs = 1.0 / tsamp_s
    P = np.abs(np.fft.rfft(x)) ** 2
    freqs = np.fft.rfftfreq(n, tsamp_s)
    if fmax_hz is None:
        fmax_hz = 0.5 * fs
    band = (freqs >= fmin_hz) & (freqs <= fmax_hz)
    if not band.any():
        return []
    base = np.median(P[band]) + 1e-30
    score = P.copy()
    harm_used = np.ones_like(P)
    for k in range(2, nharm + 1):
        j = np.rint(freqs * k / (freqs[1] - freqs[0])).astype(np.int64)
        ok = j < len(P)
        add = np.zeros_like(score)
        add[ok] = P[j[ok]]
        score = score + add
        harm_used = harm_used + ok
    score = score / (base * harm_used)

    idx = np.where(band)[0]
    order = idx[np.argsort(score[idx])[::-1]]
    out = []
    for i in order:
        f = float(freqs[i])
        if f <= 0:
            continue
        if any(abs(f - o["freq_hz"]) < 0.01 * o["freq_hz"] for o in out):
            continue
        out.append({"freq_hz": f, "period_s": 1.0 / f,
                    "power_ratio": float(score[i])})
        if len(out) >= top:
            break
    return out


def subband_dm_single(dyn, freqs_mhz, tsamp_s: float, t_peak_s: float,
                      window_s: float, nsub: int = 8, dm_guess: float | None = None,
                      width_samples: int = 8):
    """A11c — ĐO DM từ XUNG ĐƠN bằng trễ giữa các dải con (không cần chu kỳ).

    Ba cải tiến sau khi gỡ lỗi trên dữ liệu GREENBURST thật:
      1. KHỬ TÁN SẮC NỘI DẢI trước khi đo đỉnh (với dm_guess): dải thấp bị
         trải nội dải tới 26 ms (120 MHz quanh 1 GHz) → đỉnh boxcar lòe
         trong mặt phẳng, sai 10–20 ms nếu không khử.
      2. NỘI SUY PARABOL trên mẫu đỉnh → độ phân giải dưới 1 mẫu.
      3. KHỚP CÓ LOẠI NGOẠI LAI (sigma-clip): dải chứa RFI di động
         (1800–1920 MHz) cho đỉnh giả → bị loại tự động khỏi phép khớp.

    Fit: t_đo(f) = t0 + K·DM·(1/f²)  →  DM = slope/K.
    Trả về dict {dm, dm_err, t0_s, lags_s, freqs_mhz, snr_sub, used}.
    """
    dyn = np.asarray(dyn, dtype=np.float64)
    freqs = np.asarray(freqs_mhz, dtype=float)
    order = np.argsort(freqs)
    f, d = freqs[order], dyn[order]
    ntime = d.shape[1]
    f_ref = float(f.max())
    edges = np.linspace(0, len(f), nsub + 1).astype(int)
    w = max(1, int(width_samples))

    fmean, tpos, snrs = [], [], []
    for k in range(nsub):
        sl = slice(edges[k], edges[k + 1])
        f_k = float(f[sl].mean())
        if dm_guess is not None:
            # khử trải NỘI dải về tâm dải con → đỉnh sắc lại
            s, _ = dedisperse(d[sl], f[sl], float(dm_guess), tsamp_s,
                              f_ref_mhz=f_k)
        else:
            s = d[sl].mean(axis=0)
        med = np.median(s)
        rms = 1.4826 * np.median(np.abs(s - med)) + 1e-12
        if dm_guess is not None:
            t_exp = t_peak_s + K_DM * dm_guess * (1.0 / f_k**2 - 1.0 / f_ref**2)
        else:
            t_exp = t_peak_s
        i0 = max(0, int((t_exp - 3 * window_s) / tsamp_s))
        i1 = min(len(s), int((t_exp + 3 * window_s) / tsamp_s))
        seg = s[i0:i1] - med
        if len(seg) < 2 * w + 3:
            raise ValueError("cửa sổ xung quá nhỏ so với tsamp/width")
        c = np.concatenate(([0.0], np.cumsum(seg)))
        z = (c[w:] - c[:-w]) / (rms * np.sqrt(w))
        j = int(np.argmax(z))
        y0 = z[max(j - 1, 0)]; y1 = z[j]; y2 = z[min(j + 1, len(z) - 1)]
        den = y0 - 2 * y1 + y2
        delta = 0.5 * (y0 - y2) / den if abs(den) > 1e-12 else 0.0
        t_k = (i0 + j + (w - 1) / 2.0 + delta) * tsamp_s
        fmean.append(f_k); tpos.append(t_k); snrs.append(float(y1))
    fmean = np.asarray(fmean); tpos = np.asarray(tpos)
    # CHỐNG TRẢ VỀ DM RÁC: nếu không có xung thật trong cửa sổ thì báo lỗi,
    # không được lặng lặng khớp đường thẳng lên nhiễu (đã xảy ra khi gọi sai t_peak).
    if np.median(snrs) < 5.0:
        raise ValueError(
            f"không thấy xung trong cửa sổ quanh t={t_peak_s*1e3:.0f} ms "
            f"(SNR dải con trung vị {np.median(snrs):.1f} < 5)")

    # ---- khớp tuyến tính TRỌNG SỐ SNR + LOẠI NGOẠI LAI
    # (dải thấp xung bị tán xạ làm rộng → đỉnh lệch sớm; dải RFI cho đỉnh giả;
    #  trọng số SNR giảm ảnh hưởng của cả hai)
    x = 1.0 / fmean**2
    used = np.ones(len(x), dtype=bool)
    sol = np.zeros(2)
    sw_all = np.sqrt(np.maximum(snrs, 1e-9))
    for _ in range(3):
        sw = sw_all[used]
        A = np.vstack([x[used], np.ones(used.sum())]).T * sw[:, None]
        b = tpos[used] * sw
        sol, *_ = np.linalg.lstsq(A, b, rcond=None)
        resid = tpos - (sol[0] * x + sol[1])
        r = resid[used]
        sig = 1.4826 * np.median(np.abs(r - np.median(r))) + 1e-12
        new = used & (np.abs(resid - np.median(r)) < 2.5 * sig)
        if new.sum() < 4 or (new == used).all():
            break
        used = new
    dm = float(sol[0]) / K_DM
    t0 = float(sol[1])
    rr = tpos[used] - (sol[0] * x[used] + sol[1])
    dm_err = max(abs(np.sqrt(np.mean(rr**2)) / abs(sol[0]) * dm
                     * np.sqrt(used.sum())), 0.01 * abs(dm))
    return {"dm": dm, "dm_err": dm_err, "t0_s": t0,
            "lags_s": tpos - tpos[-1],
            "freqs_mhz": fmean, "snr_sub": np.asarray(snrs),
            "used": used}


def find_pulses(series, tsamp_s: float, threshold: float = 8.0,
                widths=(1, 2, 4, 8, 16, 32, 64), min_sep_s: float | None = None):
    """A7+ — tìm NHIỀU xung đơn trên chuỗi đã khử tán sắc, có gom cụm.

    Lọc khớp boxcar đa độ rộng → ứng viên (thời điểm, độ rộng, SNR);
    gom ứng viên cách nhau < min_sep_s (mặc định = 3× bề rộng lớn nhất).
    Trả về list dict {t_s, width_samples, width_ms, snr} xếp theo SNR.
    """
    x = np.asarray(series, dtype=np.float64)
    med = np.median(x)
    rms = 1.4826 * np.median(np.abs(x - med)) + 1e-12
    d = x - med
    c = np.concatenate(([0.0], np.cumsum(d)))
    cand = []
    for w in widths:
        if w > len(d):
            continue
        s = c[w:] - c[:-w]
        z = s / (rms * np.sqrt(w))
        for i in np.where(z > threshold)[0]:
            cand.append(dict(t_s=(i + (w - 1) / 2.0) * tsamp_s,
                             width_samples=int(w), width_ms=w * tsamp_s * 1e3,
                             snr=float(z[i])))
    cand.sort(key=lambda k: -k["snr"])
    min_sep = min_sep_s if min_sep_s else 3 * max(widths) * tsamp_s
    kept = []
    for cd in cand:
        if all(abs(cd["t_s"] - k["t_s"]) > min_sep for k in kept):
            kept.append(cd)
    return kept

def mask_bursty_channels(dyn, max_ratio: float = 3.0, pct: float = 99.9):
    """A9 — loại kênh "bursty" (RFI băng hẹp có xung mạnh).

    Khác `mask_bad_channels` (chỉ nhìn MỨC trung vị), hàm này nhìn ĐỘ BURST:
        ratio = P99.9 / median
    Kênh có ratio > max_ratio chứa xung RFI mạnh → nếu giữ, khi cộng dồn
    khử tán sắc nó sẽ áp đảo toàn dải (đã gặp: 827/4096 kênh như vậy trong
    file IQRM "empty_example", làm SNR giả 1210σ, che mất tín hiệu thật).
    """
    d = np.asarray(dyn, dtype=np.float64)
    med = np.median(d, axis=1)
    hi = np.percentile(d, pct, axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = np.where(med > 0, hi / np.maximum(med, 1e-12), 1e9)
    return (ratio <= max_ratio) & (med > 0)


def zero_dm_filter(dyn, exclude_zero: bool = True):
    """A9 — Zero-DM filtering: TRỪ thành phần chung mọi kênh (PRESTO `zero_dm`).

    Vì sao cần thay vì chỉ cắt cột: RFI băng rộng (tia lửa, 10 Hz từ màn hình,
    sạc điện...) xuất hiện ở MỌI kênh cùng lúc. Xung pulsar đã tán sắc thì
    tại mỗi thời điểm chỉ có 1–2 dải con → trung vị qua các kênh KHÔNG bị ảnh
    hưởng. Do đó trừ "common mode" diệt RFI mà giữ nguyên xung.

    u(t) = median_over_channels( D[ν,t] − nền_kênh[ν] )
    D'[ν,t] = D[ν,t] − u(t)

    Trả về (dyn', u) với u là chuỗi zero-DM (dùng để chẩn đoán/vẽ).
    """
    d = np.asarray(dyn, dtype=np.float64)
    base = np.median(d, axis=1, keepdims=True)
    x = d - base
    u = np.median(x, axis=0) if exclude_zero else np.zeros(d.shape[1])
    return x - u[None, :], u


def zero_dm_snr_ratio(snr_dm: float, snr_zero_dm: float) -> float:
    """Tỷ số SNR(dm) / SNR(zero-DM) — dùng để nhận diện RFI zero-DM.

    Pulsar thật: khử tán sắc đúng DM làm xung nét hơn → tỷ số lớn.
    RFI băng rộng: SNR gần như nhau ở mọi DM → tỷ số ≈ 1.
    """
    return float(snr_dm / max(snr_zero_dm, 1e-9))


# ------------------------------------------------------------------ G: RFI (A9)
def spectral_kurtosis(dyn, navg: int = 64):
    """A9 — Spectral Kurtosis (Nita & Gary 2010): 1 = nhiễu Gaussian, >1 = RFI.

    Chia trục thời gian thành các block navg mẫu, tính SK cho từng kênh.
    """
    d = np.asarray(dyn, dtype=np.float64)
    n = d.shape[1] // navg
    if n < 1:
        raise ValueError("navg lớn hơn số mẫu thời gian")
    x = d[:, : n * navg].reshape(d.shape[0], n, navg)
    s1 = x.sum(axis=2)
    s2 = (x**2).sum(axis=2)
    sk = (navg + 1) / (navg - 1) * (navg * s2 / (s1**2 + 1e-30) - 1.0)
    return sk.mean(axis=1)


def zero_dm_excise(dyn, threshold: float = 6.0, replace: str = "median",
                   keep_dispersed: bool = True, flatness_max: float = 0.35,
                   nsub: int = 8):
    """A9 — cắt RFI "zero-DM": xung RFI xuất hiện ĐỒNG THỜI mọi kênh.

    CẢNH BÁO ĐÃ GẶP THẬT (dữ liệu GREENBURST): xung pulsar CŨNG nâng trung
    bình toàn dải khi quá mạnh (vệt tán sắc chiếm ~15% kênh mỗi thời điểm).
    Cắt bừa = XOÁ ĐÚNG TÍN HIỆU (3 vệt × ~350 mẫu ≈ 13% số mẫu).
    Vì vậy mặc định keep_dispersed=True: chỉ cắt khi phần thừa trải ĐỀU
    trên phổ (RFI băng rộng), giữ khi tập trung theo tần số (xung tán sắc
    chỉ hiện diện trong 1–2 dải con tại mỗi thời điểm).

    Tiêu chí phổ: chia nsub dải con, frac = max/sum phần thừa dương —
    RFI phẳng ≈ 1/nsub, xung tán sắc > flatness_max (0.35).

    Trả về (dyn_sạch, mask_bị_cắt).
    """
    d = np.asarray(dyn, dtype=np.float64).copy()
    ts = d.mean(axis=0)
    med = np.median(ts)
    rms = 1.4826 * np.median(np.abs(ts - med)) + 1e-12
    bad = (ts - med) > threshold * rms
    if bad.any() and keep_dispersed:
        nsub_use = max(2, min(nsub, d.shape[0] // 4))
        g = d.shape[0] // nsub_use
        sub = d[: nsub_use * g].reshape(nsub_use, g, d.shape[1]).mean(axis=1)
        ex = np.clip(sub - np.median(sub, axis=1, keepdims=True), 0.0, None)
        frac = ex.max(axis=0) / (ex.sum(axis=0) + 1e-12)
        bad = bad & (frac < flatness_max)     # chỉ cờ với RFI PHẲNG
    if bad.any():
        if replace == "median":
            d[:, bad] = np.median(d, axis=1)[:, None]
        else:
            d[:, bad] = 0.0
    return d, bad


def mask_bad_channels(dyn, sigma: float = 4.0):
    """A9 — loại kênh có công suất trung bình lệch bất thường (RFI băng hẹp)."""
    d = np.asarray(dyn, dtype=np.float64)
    m = np.median(d, axis=1)
    med = np.median(m)
    rms = 1.4826 * np.median(np.abs(m - med)) + 1e-12
    good = np.abs(m - med) < sigma * rms
    return good


def bandpass_normalize(dyn, smooth: int = 31):
    """A1 — chuẩn hoá bandpass: chia mỗi kênh cho đường nền trơn của nó."""
    d = np.asarray(dyn, dtype=np.float64)
    ref = np.median(d, axis=1, keepdims=True)
    return d / np.maximum(ref, 1e-12)


# ------------------------------------------------------- H: tiện ích hiển thị
def downsample_time(series, factor: int):
    x = np.asarray(series, dtype=np.float64)
    n = len(x) // factor
    return x[: n * factor].reshape(n, factor).mean(axis=1)


def summarize(prof, tsamp_s: float, period_s: float):
    """Tóm tắt hồ sơ xung: SNR, độ rộng (ms), pha đỉnh."""
    snr, w, ph = profile_snr(prof)
    bins_per_ms = len(prof) / (period_s * 1e3)
    return {"snr": snr, "width_bins": w, "width_ms": w / bins_per_ms,
            "phase_peak": ph}
