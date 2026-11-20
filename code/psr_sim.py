# -*- coding: utf-8 -*-
"""
psr_sim.py — Sinh dữ liệu pulsar TỔNG HỢP (dynamic spectrum) để kiểm chứng
pipeline trước khi có dữ liệu thật từ kính.

Mô hình sinh dữ liệu:
    dyn[chan, t] = nền_nhiệt_ễnh (Gaussian, sigma=1)
                 + A · exp(-z²/2)      (xung Gauss, z = (t - t0 - tau_DM(chan))/sigma_t)
                 + A · f · exp(-z/tau_sc)  với z>0   (đuôi tán xạ, tuỳ chọn)
    A được chọn ngược từ SNR mong muốn:
        SNR_fold ≈ A · sqrt(nchan · ntime · W/P)
    (đúng với nhiễu trắng đơn vị, trước khi bị trải tán sắc)

Biên độ A KHÔNG phải mJy — đây là "số sigma nhiễu mỗi mẫu kênh". Muốn quy ra
mJy thì dùng psr_sensitivity.py (ngân sách S/N của kính thật).
"""
from __future__ import annotations

import numpy as np

from psr_core import dm_delay_s


def make_freqs(nchan: int, bw_mhz: float, f_center_mhz: float):
    df = bw_mhz / nchan
    return f_center_mhz + (np.arange(nchan) - (nchan - 1) / 2.0) * df


def simulate(dm: float = 26.8, period_s: float = 0.714519,
             w50_ms: float = 12.0, nchan: int = 64, bw_mhz: float = 64.0,
             f_center_mhz: float = 1400.0, tsamp_s: float = 5e-4,
             t_total_s: float = 120.0, snr_target: float = 15.0,
             scatter_tau_ms: float = 0.0, scatter_frac: float = 0.3,
             rfi: bool = True, seed: int = 1):
    """Trả về (dyn, freqs_mhz, meta)."""
    rng = np.random.default_rng(seed)
    freqs = make_freqs(nchan, bw_mhz, f_center_mhz)
    ntime = int(round(t_total_s / tsamp_s))
    t = np.arange(ntime) * tsamp_s

    # --- nhiễu nền: radiometer noise, trung bình 1, sigma 1
    dyn = 1.0 + rng.normal(0.0, 1.0, (nchan, ntime)).astype(np.float64)

    # --- biên độ suy ngược từ SNR mong muốn
    sigma_t = (w50_ms * 1e-3) / 2.3548
    duty = min(max(w50_ms * 1e-3 / period_s, 1e-4), 0.9)
    amp = snr_target / np.sqrt(nchan * ntime * duty)

    # --- trễ tán sắc so với kênh tần số cao nhất
    delay = dm_delay_s(dm, freqs, f_ref_mhz=freqs.max())      # >= 0

    taus = np.zeros(nchan)
    if scatter_tau_ms > 0:
        taus = scatter_tau_ms * 1e-3 * (freqs / freqs.max()) ** -4.0

    npulses = int(t_total_s / period_s)
    iw = int(np.ceil(6 * sigma_t / tsamp_s)) + 2
    for k in range(npulses):
        t0 = k * period_s
        for i in range(nchan):
            c = t0 + delay[i]
            i0 = int(round((c - 4 * sigma_t) / tsamp_s))
            i1 = int(round((c + max(8 * sigma_t, 8 * taus[i])) / tsamp_s)) + 1
            if i1 <= 0 or i0 >= ntime:
                continue
            i0c, i1c = max(i0, 0), min(i1, ntime)
            tl = t[i0c:i1c]
            z = (tl - c) / sigma_t
            sig = amp * np.exp(-0.5 * z * z)
            if taus[i] > 0:
                tau = taus[i]
                tail = np.where(tl > c,
                                scatter_frac * amp * np.exp(-(tl - c) / tau),
                                0.0)
                sig = sig + tail
            dyn[i, i0c:i1c] += sig

    # --- RFI
    if rfi:
        # (a) RFI băng hẹp, liên tục: vài kênh bị "nâng" nền
        bad = rng.choice(nchan, size=max(1, nchan // 16), replace=False)
        dyn[bad, :] += rng.uniform(4.0, 12.0, size=(len(bad), 1))
        # (b) RFI xung, trải đều mọi kênh (zero-DM): máy bay, tia lửa điện...
        nb = max(3, int(t_total_s / 10))
        for _ in range(nb):
            j = rng.integers(0, ntime)
            wdt = int(rng.integers(1, 5))
            dyn[:, j:j + wdt] += rng.uniform(15.0, 40.0)

    meta = {
        "dm": dm, "period_s": period_s, "w50_ms": w50_ms,
        "nchan": nchan, "bw_mhz": bw_mhz, "f_center_mhz": f_center_mhz,
        "tsamp_s": tsamp_s, "t_total_s": t_total_s, "ntime": ntime,
        "amp_sigma": float(amp), "snr_target": snr_target,
        "npulses": npulses, "rfi": rfi,
    }
    return dyn.astype(np.float32), freqs, meta


def simulate_iq(dyn_like, nchan: int, fs_hz: float, seed: int = 2):
    """Sinh IQ phức từ một phổ công suất mong muốn (để test channelize/A3).

    Không cần cho pipeline chính — dùng khi muốn thử nghiệm khử tán sắc kết hợp.
    """
    rng = np.random.default_rng(seed)
    ntime = 512
    iq = (rng.normal(0, 1, ntime * nchan)
          + 1j * rng.normal(0, 1, ntime * nchan)) / np.sqrt(2)
    return iq.astype(np.complex64)


if __name__ == "__main__":
    d, f, m = simulate(t_total_s=10.0, rfi=False)
    print("dyn", d.shape, "freqs", f.min(), f.max(), "meta", m)
