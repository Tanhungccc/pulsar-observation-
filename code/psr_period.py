# -*- coding: utf-8 -*-
"""Đoạn mã M3 — dò chu kỳ mù (FFT + cộng hài + sàng hài) và Top-N ứng viên.

Được chèn vào psr_detect.py. Tách riêng để dễ đọc/sửa.
"""
from __future__ import annotations

import numpy as np

from psr_core import fft_search, fold, profile_snr, refine_period


def decimate_for_fft(series, tsamp_s: float, max_samples: int = 4_000_000,
                     t_res_s: float = 5e-4):
    """Giảm số mẫu để FFT khả thi (RAM/thời gian), giữ độ phân giải thời gian.

    - Ưu tiên tsamp hiệu dụng ≤ t_res_s (0,5 ms) để còn thấy P ngắn;
    - nhưng không để số mẫu vượt max_samples (4 M) → file 4 h sẽ xuống ~4 ms.
    Trả (series_decimated, tsamp_eff).
    """
    x = np.asarray(series, dtype=np.float64)
    f = max(1, int(np.ceil(t_res_s / tsamp_s)))
    while x.size // f > max_samples:
        f *= 2
    if f == 1:
        return x, tsamp_s
    n = (x.size // f) * f
    return x[:n].reshape(-1, f).mean(axis=1), tsamp_s * f


def sift_harmonics(cands, tol: float = 0.02, min_rel: float = 0.25):
    """A5b — SÀNG HÀI: giữ TẦN SỐ THẤP NHẤT của mỗi họ hài.

    FFT cộng hài cho điểm cao ở 2f, 3f... nên nếu xếp theo công suất thì hài
    thắng và ta báo P/2 (đã gặp: tín hiệu P = 253 ms bị báo 126,5 ms = P/2).
    Cách đúng: duyệt từ tần số THẤP lên; bỏ ứng viên là bội nguyên của một ứng
    viên đã giữ, với điều kiện ứng viên gốc có công suất ≥ min_rel × công suất
    của hài (nếu gốc quá yếu thì vẫn giữ hài).
    """
    kept = []
    for c in sorted(cands, key=lambda x: float(x["freq_hz"])):
        f = float(c["freq_hz"])
        if f <= 0:
            continue
        is_harm = False
        for o in kept:
            r = f / float(o["freq_hz"])
            k = round(r)
            if (k >= 2 and abs(r - k) <= tol * k
                    and float(o["power_ratio"]) >= min_rel * float(c["power_ratio"])):
                is_harm = True
                break
        if not is_harm:
            kept.append(c)
    return kept


def count_profile_peaks(prof, rel: float = 0.5, min_sep_bins: int = 3) -> int:
    """Đếm số đỉnh đáng kể trong hồ sơ (có xét vòng). Dùng để loại P bội.

    Pulsar thật tại P đúng chỉ có MỘT xung chính mỗi chu kỳ; nếu fold tại 2P thì
    hồ sơ có 2 xung → đó không phải chu kỳ cơ bản.
    """
    p = np.asarray(prof, dtype=float)
    if p.size < 8:
        return 0
    med = float(np.median(p))
    hi = float(np.max(p))
    if hi <= med:
        return 0
    thr = med + rel * (hi - med)
    hot = p >= thr
    # gộp cụm liên tiếp (có vòng)
    idx = np.where(hot)[0]
    if idx.size == 0:
        return 0
    groups = 1
    for a, b in zip(idx[:-1], idx[1:]):
        if b - a > min_sep_bins:
            groups += 1
    if hot[0] and hot[-1] and idx.size > 1 and (p.size - idx[-1] + idx[0]) <= min_sep_bins:
        groups -= 1
    return max(groups, 1)


def expand_harmonic_family(cands, pmax_s: float, kmax: int = 4):
    """Thêm các chu kỳ bội (2P, 3P, 4P) của mỗi ứng viên FFT.

    Vì FFT cộng hài có thể chỉ thấy 2f0 mạnh hơn f0 (xung hẹp) → phải thử cả
    chu kỳ dài hơn rồi chọn theo SNR fold + số đỉnh trong hồ sơ.
    """
    out = list(cands)
    seen = [float(c["freq_hz"]) for c in cands]
    for c in cands:
        f = float(c["freq_hz"])
        for k in range(2, kmax + 1):
            p2 = k / f
            if p2 > pmax_s:
                break
            f2 = 1.0 / p2
            if any(abs(f2 - g) < 0.02 * max(f2, g) for g in seen):
                continue
            seen.append(f2)
            out.append(dict(freq_hz=f2, period_s=p2,
                            power_ratio=float(c["power_ratio"]),
                            from_harmonic=k))
    return out


def blind_period_search(series, tsamp_s: float, fmin_hz: float = 0.1,
                        fmax_hz: float = 500.0, nharm: int = 4, top: int = 10,
                        threshold: float = 8.0, nbins: int = 256,
                        pmax_s: float | None = None):
    """Dò chu kỳ KHÔNG cần biết P: FFT + cộng hài → sàng hài → refine → xếp hạng.

    Trả dict: {searched, tsamp_eff_s, n_samples, trials, candidates:[{p_s, snr,
    power_ratio, p_fft_s, harm_ok}], best}
    """
    x, ts = decimate_for_fft(series, tsamp_s)
    if pmax_s is None:
        pmax_s = 1.0 / max(fmin_hz, 1e-6)
    fmax = min(fmax_hz, 0.5 / ts)                 # không vượt Nyquist
    fmin = max(fmin_hz, 1.0 / max(len(x) * ts, 1e-9))   # ≥ 1 bin tần số
    raw = fft_search(x, ts, fmin_hz=fmin, fmax_hz=fmax, nharm=nharm,
                     top=max(top * 3, 15))
    # KHÔNG sàng theo tần số: cộng hài làm bán hài (f0/2, f0/3) trội hơn f0
    # (vì P(f0/2)+P(f0)+P(3f0/2)… cộng cả hài thật). Thay vào đó:
    #   1) lấy các đỉnh FFT thô;  2) mở rộng họ hài k·P (k=1..4);
    #   3) fold từng chu kỳ → SNR + số đỉnh trong hồ sơ;
    #   4) chu kỳ CƠ BẢN = chu kỳ NGẮN NHẤT có 1 đỉnh và SNR gần đỉnh nhất.
    # Chặn chu kỳ phi lý: cần ≥ 5 chu kỳ quan sát và ≥ 8 mẫu mỗi chu kỳ,
    # nếu không thì fold chỉ có vài mẫu/bin → SNR bùng nổ giả (đã gặp 5,8e12σ).
    t_obs = len(x) * ts
    p_limit = t_obs / 5.0
    raw = [c for c in raw if float(c["period_s"]) <= p_limit]
    # Ghi rõ giới hạn để báo cáo/hình KHÔNG in SNR khi phép gập vô nghĩa
    fold_note = None
    if t_obs < 5 * (1.0 / max(fmax, 1e-9)):
        fold_note = ("Tệp quá ngắn để gập chu kỳ "
                     f"(T_obs = {t_obs * 1e3:.0f} ms < 5 chu kỳ ở tần số cao "
                     "nhất dò) — chỉ phù hợp dò xung đơn")
    fam_src = raw[:min(len(raw), 10)]
    family = expand_harmonic_family(fam_src, pmax_s=pmax_s)
    out = []
    for c in family:
        try:
            p1, snr1, prof1 = refine_period(x, ts, float(c["period_s"]),
                                            nbins=nbins, iters=1, nstep=11)
            _, cnt1 = fold(x, ts, float(p1), nbins=nbins)
            n_pk = count_profile_peaks(prof1)
            snr_chk, _, _, info = profile_snr(prof1, counts=cnt1,
                                              return_info=True)
        except Exception:
            continue
        if float(p1) > p_limit or float(p1) / ts < 8:
            continue
        # LOẠI ứng viên mà phép gập không đủ mẫu nền:
        #   · số bin có mẫu < 25 % nbins  → hồ sơ răng lược
        #   · ước lượng nền suy biến (MAD sụp) → SNR không có ý nghĩa thống kê
        n_fill = int(info.get("n_filled", 0))
        # Tiêu chí Đếm mẫu trên bin: MAD cần ≥ ~5 mẫu/bin mới là ước lượng
        # thống kê. Tệp 1 xung (325 mẫu / 101 bin ≈ 3,2 mẫu/bin) → nền không
        # ước lượng được → phép gập vô nghĩa, phải nói rõ thay vì in SNR.
        spb = len(x) / max(n_fill, 1)
        undersampled = (n_fill < 0.25 * nbins) or bool(info.get("degenerate"))             or spb < 5.0
        if undersampled:
            if fold_note is None:
                fold_note = (f"Tệp quá ngắn để gập chu kỳ: {len(x)} mẫu chia "
                             f"{n_fill}/{nbins} bin có dữ liệu ≈ {spb:.1f} mẫu/bin"
                             " (< 5) → nền không ước lượng được, SNR fold vô "
                             "nghĩa. Dữ liệu chỉ phù hợp DÒ XUNG ĐƠN "
                             "(1 giant pulse / dưới 5 chu kỳ).")
            continue
        if abs(snr_chk - float(snr1)) > max(1.0, 0.2 * abs(snr1)):
            snr1 = snr_chk                # dùng giá trị đã chống suy biến
        score = min(float(snr1), 1e4) * (1.0 if n_pk == 1 else 0.4)
        out.append(dict(p_s=round(float(p1), 9), snr=round(float(snr1), 2),
                        score=round(score, 2), n_peaks=int(n_pk),
                        n_filled_bins=n_fill,
                        power_ratio=round(float(c.get("power_ratio", 0)), 2),
                        p_fft_s=round(float(c["period_s"]), 6)))
    # bỏ trùng (chu kỳ gần nhau < 1 %) — giữ điểm cao hơn
    uniq = []
    for c in sorted(out, key=lambda r: -r["score"]):
        if all(abs(c["p_s"] - u["p_s"]) > 0.01 * c["p_s"] for u in uniq):
            uniq.append(c)
    out = uniq
    out.sort(key=lambda r: -r["score"])
    best = out[0] if out else None
    if best is not None:
        for c in out:                       # ưu tiên CHU KỲ CƠ BẢN (ngắn nhất)
            if (c["p_s"] < best["p_s"] and c["n_peaks"] == 1
                    and c["snr"] >= 0.8 * best["snr"]):
                best = c
        # tinh chỉnh lần cuối ở chu kỳ đã chọn
        try:
            p_b, snr_b, _ = refine_period(x, ts, float(best["p_s"]),
                                          nbins=nbins, iters=2, nstep=15)
            if snr_b >= 0.9 * best["snr"]:
                best = dict(best, p_s=round(float(p_b), 9), snr=round(float(snr_b), 2))
        except Exception:
            pass
    if best is not None and best["snr"] < threshold:
        fold_note = (f"Không chu kỳ nào vượt ngưỡng {threshold:.0f}σ "
                     f"(tốt nhất {best['snr']:.1f}σ tại P = "
                     f"{best['p_s'] * 1e3:.2f} ms)")
    return dict(searched=True, tsamp_eff_s=float(ts), n_samples=int(len(x)),
                trials=int(len(x)), fmin_hz=fmin, fmax_hz=fmax,
                n_fft_candidates=len(raw), n_after_sift=len(fam_src),
                threshold=threshold, n_family=len(family), candidates=out,
                fold_note=fold_note, t_obs_s=float(t_obs),
                n_cycles_min=5,
                best=best if (best and best["snr"] >= threshold) else None)


def plot_period_search(res, ax=None, title="", tag=True):
    """Hình M3: phổ công suất (vùng tốt nhất) + hồ sơ fold tại P tốt nhất."""
    import matplotlib.pyplot as plt
    import psr_plots as pp
    if ax is None:
        _, axs = plt.subplots(1, 2, figsize=(11.0, 3.4))
    else:
        axs = ax
    best = (res or {}).get("best")
    cands = (res or {}).get("candidates") or []
    a0 = axs[0]
    if cands:
        names = [f"P={c['p_s'] * 1e3:.2f} ms" for c in cands[:8]]
        vals = [c["snr"] for c in cands[:8]]
        a0.barh(range(len(vals))[::-1], vals, color=pp.C_FIT, height=0.62)
        a0.set_yticks(range(len(vals))[::-1])
        a0.set_yticklabels(names, fontsize=8)
        a0.set_xlabel("SNR fold (σ)")
        a0.axvline(res.get("threshold", 8.0), color=pp.C_PULSE, ls="--", lw=1.2,
                   label=f"ngưỡng {res.get('threshold', 8.0):.0f}σ")
        a0.legend(loc="lower right", fontsize=8)
        a0.set_title(title or "Dò chu kỳ mù — Top-N ứng viên")
    # panel phải: hồ sơ fold tại P tốt nhất (nếu có)
    if best is not None and res.get("profile") is not None:
        prof = np.asarray(res["profile"], float)
        med = float(np.median(prof))
        mad = 1.4826 * float(np.median(np.abs(prof - med)))
        std = float(np.std(prof))
        # sàn chống suy biến: MAD sụp → dùng std; vẫn 0 → dùng thang dữ liệu
        floor = max(std, float(np.max(prof) - med)) * 1e-3
        mad = max(mad, std if mad <= 0.05 * std else 0.0, floor, 1e-30)
        y = (prof - med) / mad
        ph = np.arange(prof.size) / prof.size
        axs[1].plot(np.r_[ph, ph + 1], np.r_[y, y], lw=1.0, color=pp.C_FIT)
        axs[1].set_xlabel("pha (chu kỳ)")
        axs[1].set_ylabel("tín hiệu (σ)")
        _snr = float(best["snr"])
        axs[1].set_title(f"Fold tại P = {best['p_s'] * 1e3:.3f} ms · "
                         + (f"SNR {_snr:.1f}" if _snr < 1e4 else "SNR không xác định"))
    else:
        _note = res.get("fold_note") or "không có ứng viên vượt ngưỡng"
        axs[1].text(0.5, 0.5, _note, ha="center", va="center", fontsize=8.5,
                    color="0.35", wrap=True, maxwidth=0.9,
                    transform=axs[1].transAxes)
        axs[1].set_title("Hồ sơ fold — không đủ cơ sở để gập")
    if tag:
        pp._tag(axs[0].figure)
    return axs
