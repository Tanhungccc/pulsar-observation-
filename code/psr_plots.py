# -*- coding: utf-8 -*-
"""
psr_plots.py — Vẽ biểu đồ CHUẨN cho kết quả quan sát pulsar.

Quy tắc bắt buộc (để không bao giờ sai ký hiệu):
    - mọi trục PHẢI có tên + đơn vị;
    - mọi giá trị in trên hình PHẢI lấy từ cùng dict metrics với file JSON;
    - chú giải mô tả đúng dòng đang vẽ (màu/ký hiệu khớp);
    - dấu thập phân dùng dấu chấm; nhãn tiếng Việt không dấu chết (UTF-8);
    - watermark "DỮ LIỆU THẬT / MÔ PHỎNG" rõ ràng ở góc.
"""
from __future__ import annotations

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import AutoMinorLocator

plt.rcParams.update({
    "font.size": 9.5,
    "axes.titlesize": 10.5,
    "axes.labelsize": 10,
    "legend.fontsize": 8.5,
    "figure.dpi": 130,
    "savefig.dpi": 130,
    "axes.grid": True,
    "grid.alpha": 0.25,
    "xtick.minor.visible": True,
    "ytick.minor.visible": True,
    "font.family": "DejaVu Sans",
})

C_PULSE = "#d62728"     # đỏ: tín hiệu pulsar
C_NOISE = "#7f7f7f"     # xám: nền/nhiễu
C_FIT = "#1f77b4"       # xanh: đường khớp/đo
C_TRUE = "#2ca02c"      # xanh lá: giá trị tham chiếu (catalogue/mô phỏng)
C_RFI = "#ff7f0e"       # cam: RFI


def _tag(ax, text="DỮ LIỆU THẬT"):
    ax.text(0.99, 0.02, text, transform=ax.transAxes, ha="right", va="bottom",
            fontsize=7.5, color="0.4",
            bbox=dict(boxstyle="round,pad=0.25", fc="white", ec="0.7", alpha=0.8))


def plot_waterfall(dyn, freqs_mhz, tsamp_s, ax=None, title="", db=True,
                   t_max_s=None, label_cbar="công suất tương đối"):
    """Waterfall tần số × thời gian. Đơn vị rõ ràng, không ngắt nhầm trục."""
    if ax is None:
        _, ax = plt.subplots(figsize=(7.2, 3.6))
    d = np.asarray(dyn, dtype=np.float64)
    if t_max_s:
        d = d[:, : int(t_max_s / tsamp_s)]
    img = 10 * np.log10(np.maximum(d, 1e-12)) if db else d
    lo = np.percentile(img, 5); hi = np.percentile(img, 99.5)
    im = ax.imshow(img, aspect="auto", origin="lower", cmap="viridis",
                   vmin=lo, vmax=hi,
                   extent=[0.0, img.shape[1] * tsamp_s * 1e3,
                           freqs_mhz[0], freqs_mhz[-1]])
    cb = plt.colorbar(im, ax=ax, pad=0.02)
    cb.set_label(label_cbar + (" (dB)" if db else ""))
    ax.set_xlabel("thời gian kể từ đầu file (ms)")
    ax.set_ylabel("tần số (MHz)")
    ax.set_title(title)
    ax.yaxis.set_minor_locator(AutoMinorLocator(2))
    return ax


def plot_timeseries(t_s, series, peaks=None, ax=None, title="",
                    ylabel="công suất chuẩn hoá", unit="ms"):
    if ax is None:
        _, ax = plt.subplots(figsize=(7.2, 2.6))
    t = np.asarray(t_s) * (1e3 if unit == "ms" else 1.0)
    ax.plot(t, series, lw=0.7, color=C_NOISE, label="chuỗi thời gian")
    if peaks:
        tp = np.array([p["t_s"] for p in peaks]) * (1e3 if unit == "ms" else 1.0)
        sp = np.interp(tp, t, series)
        ax.plot(tp, sp, "v", color=C_PULSE, ms=9, mew=0.5, mec="k", zorder=5,
                label=f"xung phát hiện (n={len(peaks)})")
    ax.set_xlabel(f"thời gian ({unit})")
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.legend(loc="upper right")
    _tag(ax)
    return ax


def plot_dm_curve(dm_grid, snr, dm_meas=None, dm_true=None, ax=None,
                  title="Quét DM — xung đơn", ylabel="SNR lọc khớp tốt nhất"):
    if ax is None:
        _, ax = plt.subplots(figsize=(7.2, 3.0))
    ax.plot(dm_grid, snr, ".-", ms=3.5, lw=1.0, color=C_FIT,
            label="SNR theo DM (đo)")
    if dm_true is not None:
        ax.axvline(dm_true, color=C_TRUE, ls="--", lw=1.4,
                   label=f"DM tham chiếu = {dm_true:.2f} pc cm$^{{-3}}$")
    if dm_meas is not None:
        ax.axvline(dm_meas, color=C_PULSE, ls=":", lw=1.8,
                   label=f"DM đo được = {dm_meas:.2f} pc cm$^{{-3}}$")
    ax.set_xlabel("DM (pc cm$^{{-3}}$)")
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.legend(loc="upper right")
    _tag(ax)
    return ax


def plot_pulse_profile(t_ms, prof, peaks, metrics, ax=None,
                       title="Hồ sơ xung (đã khử tán sắc)"):
    """Hồ sơ xung với các chú thích LẤY TỪ metrics — không bịa số."""
    if ax is None:
        _, ax = plt.subplots(figsize=(7.2, 3.0))
    ax.plot(t_ms, prof, lw=1.1, color=C_FIT, label="chuỗi đã khử tán sắc")
    for i, p in enumerate(peaks):
        ax.axvline(p["t_s"] * 1e3, color=C_PULSE, ls="--", lw=1.0,
                   label=f"xung {i+1}: t = {p['t_s']*1e3:.1f} ms, "
                         f"SNR = {p['snr']:.0f}" if i == 0 else None)
        ax.axvline(p["t_s"] * 1e3, color=C_PULSE, ls="--", lw=1.0)
    if peaks:
        ax.annotate(f"xung 1 (SNR {peaks[0]['snr']:.0f})",
                    xy=(peaks[0]["t_s"] * 1e3, prof.max()),
                    xytext=(peaks[0]["t_s"] * 1e3 + 30, prof.max() * 0.95),
                    fontsize=8, color=C_PULSE,
                    arrowprops=dict(arrowstyle="->", color=C_PULSE, lw=1))
    if "width_ms" in metrics and metrics["width_ms"] is not None:
        ax.set_title(title + f" — bề rộng đo {metrics['width_ms']:.1f} ms")
    else:
        ax.set_title(title)
    ax.set_xlabel("thời gian (ms)")
    ax.set_ylabel("công suất dư (a.u., bandpass đã chuẩn hoá)")
    ax.legend(loc="upper left")
    _tag(ax)
    return ax


def plot_subband_lags(f_mhz, lags_ms, dm_fit, dm_err, ax=None,
                      title="Trễ tán sắc giữa các dải con"):
    """lags_ms = trễ TƯƠNG ĐỐI dải tần số cao nhất (âm nếu đến sớm).
    Đường khớp: Δt(ν) = K·DM·(1/ν² − 1/ν_ref²), ν_ref = tần số cao nhất.
    """
    if ax is None:
        _, ax = plt.subplots(figsize=(7.2, 3.2))
    ax.plot(f_mhz, lags_ms, "o", color=C_FIT, ms=5,
            label="trọng tâm xung đo được (dải con)")
    xx = np.linspace(f_mhz.min(), f_mhz.max(), 120)
    f_ref = float(np.max(f_mhz))
    K = 4.148808e3
    yy = K * dm_fit * (1.0 / xx**2 - 1.0 / f_ref**2) * 1e3
    ax.plot(xx, yy, "-", color=C_PULSE, lw=1.4,
            label=f"khớp: DM = {dm_fit:.2f} ± {dm_err:.2f} pc cm$^{{-3}}$")
    ax.set_xlabel("tần số trung bình dải con (MHz)")
    ax.set_ylabel("trễ xung so với dải cao nhất (ms)")
    ax.set_title(title)
    ax.legend(loc="upper right")
    _tag(ax)
    return ax
