# -*- coding: utf-8 -*-
"""
psr_pipeline.py — Pipeline tham chiếu, chạy được end-to-end trên dữ liệu
TỔNG HỢP, để kiểm chứng TỪNG thuật toán trước khi áp lên dữ liệu thật.

Chạy:
    python psr_pipeline.py             # ~20–60 s tuỳ máy
    python psr_pipeline.py --quick     # bản rút gọn

Sản phẩm (trong ../results):
    fig01_pipeline.png   waterfall + time series + hồ sơ xung
    fig02_dm_fft.png     đường cong quét DM + phổ công suất FFT
    metrics.json         số đo: SNR trước/sau khử tán sắc, DM, P tìm được...

Các bước (đánh số khớp docs/01):
    A1  chuẩn hoá bandpass + cắt kênh hỏng
    A9  khử RFI zero-DM
    A2  khử tán sắc không kết hợp
    A11 quét DM → ước lượng DM
    A5  FFT + cộng hài → tìm chu kỳ
    A4  fold → hồ sơ xung
    A10 SNR + độ rộng xung
"""
from __future__ import annotations

import argparse
import json
import os
import time

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from psr_core import (band_smear_ms, bandpass_normalize, boxcar_snr, dedisperse,
                      dm_from_subbands,
                      ensure_utf8_stdout,
                      fft_search, fold, mask_bad_channels, profile_snr,
                      refine_period, zero_dm_excise)
from psr_sim import simulate

RESULTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "results")


def smearing_experiment(period_s=0.714519, w50_ms=12.0):
    """Thí nghiệm: khi nào KHỬ TÁN SẮC là bắt buộc ở B = 64 MHz?

    Cùng một pulsar, chỉ đổi DM: đo SNR fold khi (a) cộng thẳng toàn dải,
    (b) khử tán sắc không kết hợp từng kênh.
    """
    from psr_core import chan_smear_ms, band_smear_ms
    rows = []
    print("\n→ Thí nghiệm trải tán sắc (B = 64 MHz, 60 s, SNR đặt = 25):")
    print(f"   {'DM':>6} {'trải dải':>9} {'trải/kênh':>9} {'SNR thẳng':>10} "
          f"{'SNR khử':>8}  kết luận")
    for dm in (26.76, 100.0, 200.0, 475.0):
        d, f, m = simulate(dm=dm, period_s=period_s, w50_ms=w50_ms, rfi=False,
                           t_total_s=60.0, snr_target=25.0, seed=11,
                           tsamp_s=5e-4, nchan=64, bw_mhz=64.0)
        ts = m["tsamp_s"]
        s0 = d.mean(axis=0)
        p0, _ = fold(s0, ts, period_s, nbins=256)
        s1, _ = dedisperse(d, f, dm, ts)
        p1, _ = fold(s1, ts, period_s, nbins=256)
        a0, a1 = profile_snr(p0)[0], profile_snr(p1)[0]
        bs = band_smear_ms(dm, f.min(), f.max())
        cs = chan_smear_ms(dm, f.mean(), (f.max() - f.min()) / (len(f) - 1))
        note = ("khử tán sắc bắt buộc" if a1 > 1.5 * a0 else
                "nên khử (tăng SNR)" if a1 > 1.1 * a0 else "không cần")
        rows.append(dict(dm=dm, band_smear_ms=round(bs, 2),
                         chan_smear_ms=round(cs, 3),
                         snr_no_dedisp=round(a0, 2), snr_dedisp=round(a1, 2)))
        print(f"   {dm:>6.1f} {bs:>8.1f}ms {cs:>8.3f}ms {a0:>10.1f} "
              f"{a1:>8.1f}  {note}")
    return rows


def run(quick: bool = False):
    # GOM sản phẩm vào MỘT thư mục theo ngày (pipeline mô phỏng không có
    # file dữ liệu nguồn → mặc định đặt tên bằng ngày chạy).
    out_dir = os.path.join(RESULTS, time.strftime("%Y%m%d"))
    os.makedirs(out_dir, exist_ok=True)
    # Kịch bản mô phỏng: pulsar kiểu Vela (P = 89 ms, W50 = 3 ms, DM = 68)
    # — vừa đủ nhanh để đường cong DM sắc nét, vừa đủ chậm để thấy trải tán sắc.
    sim = dict(dm=67.94, period_s=0.089328, w50_ms=3.0, nchan=64,
               bw_mhz=64.0, f_center_mhz=1400.0,
               tsamp_s=5.0e-4 if quick else 2.5e-4,
               t_total_s=60.0 if quick else 120.0,
               snr_target=30.0, rfi=True, seed=5)
    print("→ mô phỏng:", {k: v for k, v in sim.items() if k != "seed"})
    dyn, freqs, meta = simulate(**sim)
    tsamp = meta["tsamp_s"]
    P_true, DM_true = meta["period_s"], meta["dm"]
    print(f"  dyn = {dyn.shape} ({dyn.nbytes/1e6:.0f} MB), "
          f"{meta['npulses']} xung, biên độ = {meta['amp_sigma']:.3f} sigma/mẫu")

    m = {"sim": sim, "shape": list(dyn.shape)}

    # ---------- A1: bandpass + kênh hỏng (đo trên dữ liệu THÔ)
    good = mask_bad_channels(dyn, sigma=4.0)
    dyn_c = bandpass_normalize(dyn[good])
    f_c = freqs[good]
    print(f"→ A9 cắt kênh hỏng: giữ {good.sum()}/{len(good)} kênh")

    # ---------- A9: zero-DM
    dyn_z, bad_t = zero_dm_excise(dyn_c, threshold=6.0)
    print(f"→ A9 zero-DM: cắt {bad_t.sum()}/{len(bad_t)} mẫu "
          f"({100*bad_t.mean():.2f}%)")
    m["n_chan_kept"] = int(good.sum())
    m["n_t_zero_dm"] = int(bad_t.sum())

    # ---------- A2: không khử tán sắc vs khử tán sắc
    s_raw = dyn_z.mean(axis=0)
    s_dd, dropped = dedisperse(dyn_z, f_c, DM_true, tsamp)
    print(f"→ A2 khử tán sắc tại DM={DM_true}: bỏ {dropped} mẫu đầu, "
          f"còn {len(s_dd)} mẫu")

    # ---------- A4/A10: fold tại P đúng
    prof_raw, _ = fold(s_raw, tsamp, P_true, nbins=256)
    prof_dd, _ = fold(s_dd, tsamp, P_true, nbins=256)
    snr_raw, w_raw, _ = profile_snr(prof_raw)
    snr_dd, w_dd, ph_dd = profile_snr(prof_dd)
    print(f"→ A10 SNR fold: chưa khử tán sắc = {snr_raw:6.1f} | "
          f"sau khử = {snr_dd:6.1f}  (tăng {snr_dd/max(snr_raw,1e-9):.1f}×)")
    m.update(snr_fold_no_dedisp=round(float(snr_raw), 2),
             snr_fold_dedisp=round(float(snr_dd), 2),
             width_bins_dedisp=int(w_dd),
             phase_peak=round(float(ph_dd), 4))

    # ---------- A11: quét DM
    dm_step = 0.5 if quick else max(0.5, DM_true / 120.0)
    # nbins phải >= 4*P/W50, nếu không SNR bị lượng tử hoá theo pha
    dm_grid = np.arange(0.0, 1.5 * DM_true + dm_step, dm_step)
    snr_dm = []
    for dm in dm_grid:
        s, _ = dedisperse(dyn_z, f_c, dm, tsamp)
        pr, _ = fold(s, tsamp, P_true, nbins=256)
        snr_dm.append(profile_snr(pr)[0])
    snr_dm = np.array(snr_dm)
    # làm trơn nhẹ để không chọn phải một đỉnh nhiễu đơn lẻ
    ker = np.ones(3) / 3.0
    sm = np.convolve(np.pad(snr_dm, 1, mode="edge"), ker, mode="valid")
    kbest = int(np.argmax(sm))
    dm_best = float(dm_grid[kbest])
    # Độ phân giải DM của phép quét: dịch DM một lượng sao cho trải tán sắc
    # bằng NỬA độ rộng xung thì hồ sơ bắt đầu nhoè → không phân biệt được nữa.
    w50_ms = w_dd * (P_true / 256.0) * 1e3
    delay_per_dm = max(band_smear_ms(1.0, f_c.min(), f_c.max()), 1e-6)
    dm_err = max(0.5 * w50_ms / delay_per_dm, 0.5 * dm_step)
    print(f"→ A11 DM đo được = {dm_best:.1f} ± {dm_err:.1f} "
          f"(thật {DM_true}) | SNR đỉnh = {sm[kbest]:.1f}")
    m.update(dm_true=DM_true, dm_measured=dm_best, dm_error=round(dm_err, 2),
             snr_dm_peak=round(float(sm[kbest]), 2))

    # ---------- A11b: DM chính xác từ TRỄ GIỮA CÁC DẢI CON
    # (không cần DM trước; chỉ cần chu kỳ P — đã có từ A5)
    dmsub = dm_from_subbands(dyn_z, f_c, tsamp, P_true, nsub=4, nbins=512)
    print(f"→ A11b DM (trễ dải con) = {dmsub['dm']:.2f} ± {dmsub['dm_err']:.2f} "
          f"(thật {DM_true})")
    m.update(dm_subband=round(float(dmsub["dm"]), 3),
             dm_subband_err=round(float(dmsub["dm_err"]), 3))

    # ---------- A2: khử tán sắc tại DM tốt nhất (dùng cho FFT)
    DM_use = float(dmsub["dm"])
    s_best, _ = dedisperse(dyn_z, f_c, DM_use, tsamp)

    # ---------- A5: FFT + cộng hài (chỉ SINH ỨNG VIÊN, chưa phải kết luận)
    cands = fft_search(s_best, tsamp, fmin_hz=0.5, fmax_hz=40.0, nharm=4, top=8)
    print("→ A5 top ứng viên FFT (xếp theo công suất, CHƯA kiểm chứng):")
    for i, c in enumerate(cands[:5]):
        print(f"     #{i+1}  f = {c['freq_hz']:8.4f} Hz  P = "
              f"{c['period_s']*1e3:9.3f} ms  power = {c['power_ratio']:6.1f}")

    # ---------- A5b: KIỂM CHỨNG bằng fold + tinh chỉnh chu kỳ (bắt buộc)
    # Đỉnh FFT hạng 1 thường là hài hoặc đỉnh nhiễu; chỉ fold mới phân xử được.
    verified = []
    for i, c in enumerate(cands[:5]):
        pr_, snr_, prof_ = refine_period(s_best, tsamp, c["period_s"],
                                         iters=2 if quick else 3)
        verified.append(dict(fft_rank=i + 1, period=pr_, snr=snr_,
                             power=c["power_ratio"], prof=prof_))
    verified.sort(key=lambda d: -d["snr"])
    print("→ A5b kiểm chứng bằng fold (SNR quyết định):")
    for v in verified[:4]:
        print(f"     FFT#{v['fft_rank']}  P = {v['period']*1e3:9.4f} ms  "
              f"SNR = {v['snr']:6.1f}")
    best_v = verified[0]
    P_ref, snr_ref, prof_ref = best_v["period"], best_v["snr"], best_v["prof"]
    err_ppm = (P_ref - P_true) / P_true * 1e6
    print(f"→ KẾT LUẬN: P = {P_ref*1e3:.4f} ms (lệch {err_ppm:+.1f} ppm so với "
          f"P thật {P_true*1e3:.4f} ms), SNR = {snr_ref:.1f}")
    m.update(period_true=P_true,
             fft_rank1_period=round(float(cands[0]["period_s"]), 6) if cands else None,
             fft_rank1_is_true=(abs(cands[0]["freq_hz"] * P_true - 1) < 0.01)
             if cands else None,
             period_found=round(float(P_ref), 6),
             period_err_ppm=round(float(err_ppm), 2),
             snr_fold_refined=round(float(snr_ref), 2),
             verified=[{k: (round(float(v[k]), 6) if k != "prof" else None)
                        for k in ("fft_rank", "period", "snr", "power")}
                       for v in verified[:4]])

    # ---------- A7: single pulse trên chuỗi đã khử tán sắc
    sp = boxcar_snr(s_best, widths=(1, 2, 4, 8, 16, 32))
    m["single_pulse_snr_max"] = round(float(sp[0]), 2)

    # ================= HÌNH 1: pipeline
    fig, ax = plt.subplots(2, 2, figsize=(12, 7.6))

    # (a) hồ sơ xung theo 8 dải con — CHƯA khử tán sắc: thấy đường chéo tán sắc
    nsub = 8
    step = len(f_c) // nsub
    stack = []
    for k in range(nsub):
        sl = slice(k * step, (k + 1) * step)
        psub = dyn_z[sl].mean(axis=0)
        prs, _ = fold(psub, tsamp, P_true, nbins=256)
        prs = (prs - np.median(prs)) / (1.4826 * np.median(np.abs(prs - np.median(prs))) + 1e-9)
        stack.append(prs)
    stack = np.array(stack)
    ax[0, 0].imshow(stack, aspect="auto", origin="lower", cmap="magma",
                    vmin=-1.5, vmax=4.0,
                    extent=[0, 1, f_c.min(), f_c.max()])
    ax[0, 0].set(xlabel="pha", ylabel="tần số (MHz)",
                 title="(a) 8 dải con CHƯA khử tán sắc → đường chéo tán sắc")

    # (b) kiểm chứng định luật SNR ∝ sqrt(t)
    fracs = np.linspace(0.08, 1.0, 10)
    snr_t = []
    for fr in fracs:
        n = int(fr * len(s_dd))
        prs, _ = fold(s_dd[:n], tsamp, P_true, nbins=256)
        snr_t.append(profile_snr(prs)[0])
    t_ax = fracs * len(s_dd) * tsamp
    ax[0, 1].plot(t_ax, snr_t, "o-", ms=4, label="đo từ mô phỏng")
    if snr_t[-1] > 0:
        kfit = snr_t[-1] / np.sqrt(t_ax[-1])
        ax[0, 1].plot(t_ax, kfit * np.sqrt(t_ax), "r--",
                      label="fit $\\propto\\sqrt{t}$")
    ax[0, 1].set(xlabel="thời gian tích luỹ (s)", ylabel="SNR fold",
                 title="(b) Định luật radiometer: SNR ∝ √t")
    ax[0, 1].legend(fontsize=8)

    # (c) hồ sơ xung — dịch để đỉnh nằm giữa cho dễ nhìn
    def center(p):
        k = int(np.argmax(p))
        return np.roll(p, len(p) // 2 - k)

    ph = np.arange(256) / 256
    for arr, lab, st in ((prof_raw, f"chưa khử tán sắc (SNR {snr_raw:.1f})", "-"),
                         (prof_dd, f"khử tán sắc, P đúng (SNR {snr_dd:.1f})", "-"),
                         (prof_ref, f"P do pipeline tìm (SNR {snr_ref:.1f})", "--")):
        c = center(arr)
        ax[1, 0].plot(ph, c / np.max(c), st, lw=1.3, label=lab)
    ax[1, 0].set(xlabel="pha (đã dịch đỉnh về 0.5)", ylabel="chuẩn hoá",
                 title="(c) Hồ sơ xung (fold)")
    ax[1, 0].legend(fontsize=7)

    ax[1, 1].plot(dm_grid, snr_dm, ".-", ms=4)
    ax[1, 1].axvline(DM_true, color="r", ls="--", lw=1, label="DM thật")
    ax[1, 1].axvspan(dm_best - dm_err, dm_best + dm_err, color="k", alpha=0.10)
    ax[1, 1].axvline(dm_best, color="k", ls=":", lw=1.2,
                     label=f"A11a quét DM = {dm_best:.1f} ± {dm_err:.1f}")
    ax[1, 1].axvline(DM_use, color="g", ls="-", lw=1.4,
                     label=f"A11b trễ dải con = {DM_use:.1f}")
    ax[1, 1].set(xlabel="DM (pc cm$^{-3}$)", ylabel="SNR fold",
                 title="(d) Hai cách đo DM — A11a (quét) vs A11b (trễ dải con)")
    ax[1, 1].legend(fontsize=8)
    fig.suptitle("Pipeline pulsar — dữ liệu tổng hợp RTP-3.7 "
                 f"(DM={DM_true}, P={P_true*1e3:.1f} ms)", fontsize=11)
    fig.tight_layout()
    f1 = os.path.join(out_dir, "fig01_pipeline.png")
    fig.savefig(f1, dpi=130)
    plt.close(fig)

    # ================= HÌNH 2: DM + FFT
    x = s_best - s_best.mean()
    Pw = np.abs(np.fft.rfft(x)) ** 2
    fr = np.fft.rfftfreq(len(x), tsamp)
    sel = (fr > 0.5) & (fr < 40)
    fig, ax = plt.subplots(2, 1, figsize=(11, 6.5))
    ax[0].plot(dm_grid, snr_dm, ".-", ms=4)
    ax[0].axvline(DM_true, color="r", ls="--", label="DM thật")
    ax[0].set(xlabel="DM (pc cm$^{-3}$)", ylabel="SNR fold", title="(a) Đường cong DM")
    ax[0].legend()
    fmask = (fr > 0) & (fr < 40)
    ax[1].semilogy(fr[fmask], Pw[fmask], lw=0.5, color="k")
    for k, c in enumerate(cands[:3]):
        ax[1].axvline(c["freq_hz"], color="C1", ls="--", lw=1,
                      label=f"ứng viên FFT {k+1}: {c['freq_hz']:.2f} Hz")
    for k in (1, 2, 3, 4):
        ax[1].axvline(k / P_true, color="r", ls=":", lw=1.2,
                      label="f0 thật + hài" if k == 1 else None)
    ax[1].set(xlabel="tần số (Hz)", ylabel="công suất", xlim=(0, 40),
              title="(b) Phổ công suất sau khử tán sắc — tín hiệu nằm ở f0 và các hài")
    ax[1].legend(fontsize=8)
    fig.tight_layout()
    f2 = os.path.join(out_dir, "fig02_dm_fft.png")
    fig.savefig(f2, dpi=130)
    plt.close(fig)

    m["files"] = [os.path.basename(f1), os.path.basename(f2)]
    if not quick:
        m["smearing_experiment"] = smearing_experiment()
    with open(os.path.join(out_dir, "metrics.json"), "w", encoding="utf-8") as fh:
        json.dump(m, fh, ensure_ascii=False, indent=2)
    print(f"\n→ THƯ MỤC KẾT QUẢ: {out_dir}")
    print(f"   fig01_pipeline.png, fig02_dm_fft.png, metrics.json")
    return m


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    args = ap.parse_args()
    ensure_utf8_stdout()
    run(quick=args.quick)
