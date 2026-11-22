# -*- coding: utf-8 -*-
"""numeric_audit.py — KIỂM TRA SỐ HỌC: nhắm đúng chỗ DỄ SAI SỐ NHẤT.

Mỗi phép thử so với một **chuẩn độc lập** (công thức giải tích hoặc brute-force)
và in ra **sai số đo được / dung sai**, nên không chỉ nói "chạy được" mà nói
"sai bao nhiêu".

Nhóm:
  N1  Làm tròn dịch mẫu khi khử tán sắc (nguồn sai số lớn nhất)
  N2  Lệch pha & gợn bin khi fold
  N3  Chuẩn hoá SNR: SNR giải tích (khớp lọc) vs SNR đo
  N4  Độ chính xác chu kỳ vs Cramér–Rao; dải bắt của refine_period
  N5  Công thức nhòe kênh/băng vs tích phân chính xác
  N6  Bước DM tự mở rộng vs ngân sách nhòe W50/2
  N7  float32 vs float64 (pha thời gian dài, tích luỹ nhiều kênh)
  N8  Thống kê: tỷ lệ báo động giả (SK, profile_snr, ADC, radiometer)
  N9  Đầu vào kỳ dị: kênh 0, kênh NaN, dữ liệu toàn 0, tham số 0
  N10 Pdot (Crab): cần quan sát bao lâu thì Pdot mới quan trọng
  N11 Lượng tử hoá 4-bit vs 8-bit khi có ngoại lai mạnh
  N12 Cơ số thời gian: tsamp float32, thời lượng, phát hiện mất mẫu
  N13 BỀ RỘNG HỒ SƠ: W50/W25 bất biến theo lưới độ rộng boxcar

Chạy: python numeric_audit.py            # tất cả
      python numeric_audit.py N3 N13     # vài nhóm
"""
from __future__ import annotations

import io
import contextlib
import math
import sys
import time

import numpy as np

RES = []
CUR = {"g": "?"}


def chk(name, cond, detail=""):
    ok = bool(cond)
    RES.append((CUR["g"], name, ok, detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    return ok


def num(name, value, tol, unit="", note=""):
    """Đạt nếu |value| ≤ tol."""
    return chk(name, abs(value) <= tol,
               f"{value:+.4g}{unit} (dung sai {tol:g}{unit})"
               + (f" · {note}" if note else ""))


def within(name, value, lo, hi, unit="", note=""):
    return chk(name, lo <= value <= hi,
               f"{value:.4g}{unit} (cho phép {lo:g}…{hi:g})"
               + (f" · {note}" if note else ""))


def section(g):
    CUR["g"] = g
    print(f"\n=== {g} ===")


def quiet(fn, *a, **k):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        try:
            return fn(*a, **k), None
        except Exception as exc:                 # noqa: BLE001
            return None, exc


def sim(dm, P, w50=12.0, nchan=64, bw=64.0, fc=1400.0, ts=5e-4, T=120.0,
        snr=15.0, rfi=False, seed=1):
    import psr_sim
    return psr_sim.simulate(dm=dm, period_s=P, w50_ms=w50, nchan=nchan,
                            bw_mhz=bw, f_center_mhz=fc, tsamp_s=ts,
                            t_total_s=T, snr_target=snr, rfi=rfi, seed=seed)


def dedisperse_linear(dyn, freqs, dm, ts):
    """CHUẨN ĐỘC LẬP: nội suy tuyến tính từng kênh (không làm tròn mẫu)."""
    import psr_core as C
    shift = np.asarray(C.dm_delay_s(dm, freqs, float(np.max(freqs)))) / ts
    n = dyn.shape[1] - int(np.ceil(shift.max()))
    base = np.arange(n, dtype=float)
    acc = np.zeros(n)
    for i in range(len(freqs)):
        acc += np.interp(base + shift[i], np.arange(dyn.shape[1]), dyn[i])
    return acc / len(freqs)


# ============================================================ N1 làm tròn dịch
def n1_rounding():
    section("N1 — làm tròn dịch mẫu khi khử tán sắc")
    import psr_core as C
    ts = 5e-4
    freqs = np.linspace(1400, 1420, 256)
    for dm in (2.97, 26.76, 56.77, 478.7):
        exact = C.dm_delay_s(dm, freqs, freqs.max())
        resid = (np.rint(exact / ts) * ts - exact) / ts
        print(f"     DM {dm:6.2f}: max|Δ| = {np.max(np.abs(resid)):.3f} mẫu "
              f"= {np.max(np.abs(resid))*ts*1e6:.0f} µs")
    resid = (np.rint(C.dm_delay_s(478.7, freqs, freqs.max()) / ts) * ts
             - C.dm_delay_s(478.7, freqs, freqs.max())) / ts
    chk("N1a rint không bao giờ lệch quá 0,5 mẫu", float(np.max(np.abs(resid))) <= 0.5,
        f"{np.max(np.abs(resid)):.3f} mẫu")
    chk("N1b sai số rint không lệch hệ thống", abs(float(np.mean(resid))) < 0.05,
        f"trung bình {np.mean(resid):+.3f} mẫu")

    # mất SNR thật do làm tròn — trung bình 5 seed (một seed lệch ±12 % là nhiễu)
    losses = []
    for w50, dmx, tsx, bw, nch, snr_t in ((2.0, 478.7, 5e-4, 40.0, 256, 30.0),
                                          (1.0, 300.0, 1e-4, 80.0, 256, 30.0)):
        ls = []
        for seed in range(1, 6):
            dyn, fr, _ = sim(dmx, 0.455, w50=w50, nchan=nch, bw=bw, ts=tsx,
                             T=60.0, snr=snr_t, seed=seed)
            si = C.profile_snr(C.fold(C.dedisperse(dyn, fr, dmx, tsx)[0],
                                      tsx, 0.455, nbins=256)[0])[0]
            sl = C.profile_snr(C.fold(dedisperse_linear(dyn, fr, dmx, tsx),
                                      tsx, 0.455, nbins=256)[0])[0]
            ls.append((si - sl) / sl * 100)
        losses.append(np.mean(ls))
        print(f"     W50 {w50:g} ms, DM {dmx:g}: mất SNR từng seed "
              + " ".join(f"{x:+.1f}%" for x in ls)
              + f" → trung bình {np.mean(ls):+.2f}%")
    chk("N1c làm tròn mất ≤ 6 % SNR (trung bình 5 seed, xung hẹp + DM cao)",
        all(abs(v) <= 6.0 for v in losses),
        " · ".join(f"{v:+.2f} %" for v in losses))


# =============================================================== N2 fold / pha
def n2_fold():
    section("N2 — lệch pha và gợn bin khi fold")
    import psr_core as C
    rng = np.random.default_rng(21)
    P, ts = 0.714519, 5e-4
    n = 240_000
    prof, cnt = C.fold(rng.normal(0, 1, n), ts, P, nbins=256)
    ripple = (cnt.max() - cnt.min()) / cnt.mean()
    num("N2a gợn số mẫu/bin ≤ 2 %", ripple * 100, 2.0, unit=" %",
        note=f"{cnt.min()}–{cnt.max()} mẫu/bin")
    chk("N2b hồ sơ nhiễu thuần không sinh xung giả > 4,6σ",
        C.profile_snr(prof)[0] < 4.6, f"{C.profile_snr(prof)[0]:.2f}σ")

    tt = np.arange(n) * ts
    yy = (10 * np.exp(-0.5 * (((tt % P) / P - 0.371) / 0.01) ** 2)
          + rng.normal(0, 1, n))
    ph = {}
    for nb in (64, 128, 256, 512, 1024):
        pb, _ = C.fold(yy, ts, P, nbins=nb)
        ph[nb] = int(np.argmax(pb)) / nb
    worst = max(abs(v - ph[256]) - 1.0 / min(256, nb) for nb, v in ph.items())
    chk("N2c vị trí đỉnh ổn định theo nbins (trong 1 bin của lưới đó)",
        worst <= 1.0 / 256 + 1e-9,
        "pha " + ", ".join(f"{nb}:{v:.3f}" for nb, v in ph.items()))
    num("N2d đỉnh đúng pha 0,371 (≤ 1 bin@256)", ph[256] - 0.371, 1 / 256)
    p2, _ = C.fold(yy, ts, P, nbins=256, t0_s=P * 0.25)
    p1, _ = C.fold(yy, ts, P, nbins=256)
    d = (int(np.argmax(p2)) - int(np.argmax(p1))) / 256
    err = min(abs(d - 0.75), abs(d - 0.75 + 1), abs(d - 0.75 - 1))
    chk("N2e t0_s xoay pha đúng (mod 1)", err <= 1 / 256 + 1e-9,
        f"xoay {d:+.3f}, kỳ vọng −0,25 ≡ 0,75")


# ============================================================== N3 chuẩn SNR
def n3_snr():
    section("N3 — chuẩn hoá SNR vs công thức khớp lọc giải tích")
    import psr_core as C
    ratios = []
    for snr_t, dmx, nchan, T, bw in ((30.0, 26.8, 64, 120.0, 64.0),
                                     (50.0, 56.77, 128, 240.0, 50.0),
                                     (20.0, 2.97, 256, 180.0, 32.0)):
        ts = 5e-4
        dyn, fr, meta = sim(dmx, 0.714519, w50=12.0, nchan=nchan, bw=bw, ts=ts,
                            T=T, snr=snr_t, seed=int(snr_t) + nchan)
        s, _ = C.dedisperse(dyn, fr, dmx, ts)
        m = C.profile_snr(C.fold(s, ts, 0.714519, nbins=256)[0])[0]
        # SNR giải tích: A·√nchan·√Σφ² · √N_chu_kỳ (khớp lọc tối ưu)
        A = float(meta["amp_sigma"])
        sig = float(meta["w50_ms"]) * 1e-3 / 2.35482
        tt = np.arange(-80, 81) * ts
        phi = np.exp(-0.5 * (tt / sig) ** 2)
        ncyc = float(meta["npulses"])
        th = A * math.sqrt(nchan) * math.sqrt(float(np.sum(phi ** 2))) * math.sqrt(ncyc)
        ratios.append(m / th)
        print(f"     SNR tiêm {snr_t:4.0f} | giải tích {th:6.1f} | đo {m:6.1f} "
              f"| tỷ số {m/th:.3f} [{nchan} kênh, {T:.0f} s, {ncyc:.0f} chu kỳ]")
    r = np.array(ratios)
    within("N3a SNR đo / SNR giải tích ∈ [0,70 ; 1,15]", r.mean(), 0.70, 1.15,
           note="profile_snr dùng lọc hộp nên hơi bảo thủ")
    num("N3b độ tản tỷ số giữa các cấu hình ≤ 15 %", (r.max() - r.min()) * 100,
        15.0, unit=" %")
    dyn1, fr1, _ = sim(26.8, 0.714519, nchan=64, T=120.0, snr=10.0, seed=77)
    dyn3, _, _ = sim(26.8, 0.714519, nchan=64, T=120.0, snr=30.0, seed=77)
    g = (C.profile_snr(C.fold(C.dedisperse(dyn3, fr1, 26.8, 5e-4)[0], 5e-4,
                              0.714519)[0])[0]
         / C.profile_snr(C.fold(C.dedisperse(dyn1, fr1, 26.8, 5e-4)[0], 5e-4,
                                0.714519)[0])[0])
    num("N3c SNR tuyến tính theo biên độ (×3 → 3,0 ± 0,3)", g - 3.0, 0.3)


# =========================================================== N4 chu kỳ / hài
def n4_period():
    section("N4 — chu kỳ: Cramér–Rao và dải bắt của refine_period")
    import psr_core as C
    rng = np.random.default_rng(31)
    P, ts, T = 0.714519, 5e-4, 600.0
    n = int(T / ts)
    t = np.arange(n) * ts
    duty = 0.02
    sig = duty * P / 2.3548
    x = (30 * np.exp(-0.5 * (((t % P) - duty * P * 0.4) / sig) ** 2)
         + rng.normal(0, 1, n))
    # (a) từ lệch 200 ppm (đúng điều kiện dùng thật: P catalogue ~1e-4)
    p_b, _, _ = C.refine_period(x, ts, P * (1 + 200e-6), nbins=256, iters=3, nstep=41)
    err = (p_b - P) / P
    snr_p = C.profile_snr(C.fold(x, ts, p_b)[0])[0]
    crb = duty / (snr_p * math.sqrt(T / P))
    chk("N4a |δP/P| ≤ 10×CRB (đo được không tệ hơn 10 lần giới hạn lý thuyết)",
        abs(err) / crb <= 10.0,
        f"{abs(err)/crb:.2f}× CRB · δP/P {err*1e6:+.2f} ppm · "
        f"CRB ≈ {crb*1e6:.2f} ppm · SNR {snr_p:.0f}")
    num("N4b hội tụ < 50 ppm khi khởi đầu lệch 200 ppm", abs(err) * 1e6, 50.0,
        unit=" ppm")
    # (b) dải bắt ≈ P/T (một chu kỳ trên độ dài quan sát)
    p_1k, _, _ = C.refine_period(x, ts, P * (1 + 1000e-6), nbins=256, iters=3)
    num("N4c vẫn hội tụ từ 1 000 ppm (dải bắt ≈ P/T)",
        abs((p_1k - P) / P) * 1e6, 100.0, unit=" ppm")
    p_3k, snr_3k, _ = C.refine_period(x, ts, P * (1 + 3000e-6), nbins=256, iters=3)
    chk("N4d ngoài dải bắt 3 000 ppm thì KHÔNG hội tụ (giới hạn đã biết, "
        "phải dò mù trước rồi mới refine)", snr_3k < 0.5 * snr_p,
        f"SNR {snr_3k:.0f} vs {snr_p:.0f}")
    # (c) SNR ∝ √T, trung bình 5 seed
    gs = []
    for seed in range(5):
        r2 = np.random.default_rng(100 + seed)
        xx = (30 * np.exp(-0.5 * (((t % P) - duty * P * 0.4) / sig) ** 2)
              + r2.normal(0, 1, n))
        gs.append(C.profile_snr(C.fold(xx, ts, P)[0])[0]
                  / C.profile_snr(C.fold(xx[: n // 2], ts, P)[0])[0])
    num("N4e SNR ∝ √T (T/2 → SNR/√2), trung bình 5 seed",
        float(np.mean(gs)) - math.sqrt(2), 0.06, note=f"×{np.mean(gs):.3f}")


# ============================================================ N5 công thức nhòe
def n5_smear():
    section("N5 — công thức nhòe vs tích phân chính xác")
    import psr_core as C
    for dm, fc, bw, nchan in ((26.76, 1420.0, 20.0, 256),
                              (56.77, 1420.0, 50.0, 512),
                              (478.7, 423.0, 20.0, 256)):
        df = bw / nchan
        exact = abs(float(C.dm_delay_s(dm, fc - df / 2, fc + df / 2))) * 1e3
        fm = C.chan_smear_ms(dm, fc, df)
        num(f"N5a nhòe/kênh DM {dm:g} @{fc:.0f}: lệch ≤ 5 %",
            (fm - exact) / exact * 100, 5.0, unit=" %",
            note=f"{fm:.2f} vs {exact:.2f} ms")
        eb = abs(float(C.dm_delay_s(dm, fc - bw / 2, fc + bw / 2))) * 1e3
        fb = C.band_smear_ms(dm, fc - bw / 2, fc + bw / 2)
        num(f"N5b nhòe/băng DM {dm:g} @{fc:.0f}: lệch ≤ 5 %",
            (fb - eb) / eb * 100, 5.0, unit=" %", note=f"{fb:.1f} vs {eb:.1f} ms")


# ======================================================== N6 bước DM / ngân sách
def n6_dmstep():
    section("N6 — bước DM vs ngân sách nhòe W50/2")
    import psr_core as C

    def step_ms(step, f_lo, f_hi):
        return abs(float(C.dm_delay_s(step, f_lo, f_hi))) * 1e3

    for name, f_lo, f_hi, w50, step in (
            ("B0329+54 @423 (20 MHz)", 413.0, 433.0, 5.0, 0.25),
            ("B1641-45 @423 (bước tự mở rộng)", 413.0, 433.0, 180.0, 0.718),
            ("B0833-45 @1420 (10 MHz)", 1415.0, 1425.0, 3.0, 0.25)):
        d = step_ms(step, f_lo, f_hi)
        chk(f"N6a {name}: trễ/bước {d:.2f} ms ≤ W50/2 = {w50/2:.1f} ms",
            d <= w50 / 2, f"dùng {d/(w50/2)*100:.0f} % ngân sách")
    d5 = step_ms(50.0, 413.0, 433.0)
    chk("N6b bước 50 DM vượt ngân sách W50/2 = 90 ms ở B1641-45 (phép kiểm "
        "có tác dụng)", d5 > 90.0,
        f"{d5:.0f} ms · bước tối đa còn dùng được ≈ "
        f"{90.0/step_ms(1.0, 413.0, 433.0):.0f} DM")
    ddm = 3.0 / (abs(float(C.dm_delay_s(1.0, 1395.0, 1445.0))) * 1e3)
    chk("N6c độ phân giải DM hữu hạn và hợp lý (W50 3 ms / 50 MHz)",
        1e-4 < ddm < 1e3, f"ΔDM ≈ {ddm:.3f} pc cm⁻³")


# ================================================================= N7 độ chính xác
def n7_precision():
    section("N7 — float32 vs float64")
    import psr_core as C
    rng = np.random.default_rng(41)
    nchan, ntime = 4096, 2000
    dyn = 1.0 + rng.normal(0, 0.3, (nchan, ntime))
    freqs = np.linspace(1420, 1400, nchan)
    a, _ = C.dedisperse(dyn, freqs, 26.76, 5e-4)
    b, _ = C.dedisperse(dyn.astype(np.float32), freqs, 26.76, 5e-4)
    rel = float(np.max(np.abs(a - b)) / np.std(a))
    num("N7a tích luỹ 4096 kênh: float32 lệch ≤ 1 % σ", rel * 100, 1.0, unit=" %")
    ts, P = 64e-6, 0.089328
    n = 225_000_000
    ph32 = float(np.mod((np.arange(n, dtype=np.float32) * np.float32(ts))[-1]
                        / np.float32(P), 1.0))
    ph64 = float(np.mod((np.arange(n, dtype=np.float64) * ts)[-1] / P, 1.0))
    err = abs(ph32 - ph64)
    chk("N7b float32 sẽ lệch pha đáng kể ở 4 h (nên dùng float64)", err > 1e-3,
        f"chênh pha float32 = {err*100:.3f} % vòng")
    prof, _ = C.fold(np.zeros(2_000_000), ts, P, nbins=64)
    chk("N7c fold 2e6 mẫu: hữu hạn (đang dùng float64)", np.all(np.isfinite(prof)))
    t_test = 61234.567
    e32 = abs(float(np.float32(t_test)) - t_test)
    chk("N7d tstart giây lẻ (61234,567 s): float32 lệch ≥ 0,3 ms → phải float64",
        e32 >= 3e-4, f"lệch {e32*1e3:.2f} ms (bước lượng tử float32 ≈ "
                     f"{2**-8*1e3:.2f} ms tại 6,1e4 s)")


# =============================================================== N8 thống kê
def n8_stats():
    section("N8 — tỷ lệ báo động giả")
    import ingest_guard as G
    import psr_core as C
    rng = np.random.default_rng(51)
    fp = 0
    for _ in range(100):
        d = np.abs(rng.normal(size=(400, 16))) ** 2
        fp += len(G.spectral_kurtosis(d)["bad_channels"]) > 0
    chk("N8a SK: báo động giả trên nhiễu Gauss ≤ 5 %", fp / 100 <= 0.05, f"{fp}/100")
    mx = np.array([C.profile_snr(C.fold(rng.normal(0, 1, 50_000), 5e-4,
                                        0.714519)[0])[0] for _ in range(100)])
    chk("N8b profile_snr nhiễu: max < 5σ", mx.max() < 5.0,
        f"max {mx.max():.2f}σ · TB {mx.mean():.2f}σ · p95 {np.percentile(mx, 95):.2f}σ")
    chk("N8c profile_snr nhiễu: trung bình ≤ 3,5σ", mx.mean() <= 3.5,
        f"{mx.mean():.2f}σ")
    bad = sum(G.adc_clipping(rng.normal(size=8192) * 8, 8)["tag"] == "ABORT"
              for _ in range(200))
    chk("N8d ADC: 0/200 ABORT oan trên nhiễu sạch", bad == 0, f"{bad}/200")
    warns = sum(G.radiometer_check(1.0 + rng.normal(0, 0.05, (500, 16)),
                                   1e4, 1e-3)["tag"] != "OK" for _ in range(20))
    chk("N8e radiometer: ≤ 10 % cảnh báo trên dữ liệu ổn định", warns / 20 <= 0.10,
        f"{warns}/20")


# =============================================================== N9 kỳ dị
def n9_degenerate():
    section("N9 — đầu vào kỳ dị")
    import psr_core as C
    import ingest_guard as G
    rng = np.random.default_rng(61)
    freqs = np.linspace(1420, 1400, 32)
    d = 1.0 + rng.normal(0, 0.1, (32, 500))
    d[5, :] = 0.0
    out, err = quiet(C.bandpass_normalize, d)
    chk("N9a kênh toàn 0: không NaN/Inf",
        err is None and np.all(np.isfinite(out)), type(err).__name__ if err else "")
    d2 = 1.0 + rng.normal(0, 0.1, (32, 500))
    d2[7, :] = np.nan
    out2, err2 = quiet(C.bandpass_normalize, d2)
    ok2 = err2 is None and np.isfinite(np.nanmedian(out2))
    chk("N9b kênh toàn NaN: không crash, NaN không lan", ok2,
        type(err2).__name__ if err2 else "")
    s, _ = C.dedisperse(np.zeros((32, 1000)), freqs, 10.0, 5e-4)
    p, _ = C.fold(s, 5e-4, 0.5, nbins=64)
    chk("N9c dữ liệu toàn 0: hồ sơ hữu hạn", np.all(np.isfinite(p)))
    dn = rng.normal(0, 1, (32, 4000))
    s2, _ = C.dedisperse(dn, freqs, 26.76, 5e-4)
    chk("N9d dữ liệu âm: profile_snr hữu hạn",
        np.isfinite(C.profile_snr(C.fold(s2, 5e-4, 0.714519)[0])[0]))
    # N9e: tsamp/P bằng 0 phải ném lỗi (không trả hồ sơ rác)
    raised = 0
    for fn, args in ((C.fold, (np.zeros(100), 0.0, 0.5)),
                     (C.fold, (np.zeros(100), 1e-3, 0.0)),
                     (C.fold, (np.zeros(100), -1e-3, 0.5)),
                     (C.dedisperse, (np.zeros((4, 100)), freqs[:4], 1.0, 0.0))):
        try:
            fn(*args)
        except ValueError:
            raised += 1
    chk("N9e tsamp=0 / P=0 / P âm: ném ValueError (không lặng lẽ trả rác)",
        raised == 4, f"{raised}/4")
    ramp = np.tile(np.arange(500, dtype=float), (4, 1))
    ramp[2, 100] = np.nan
    ramp[2, 300] = np.nan
    fixed, rep = G.sanitize_nonfinite(ramp)
    err3 = float(np.max(np.abs(fixed[2] - np.arange(500.0))))
    chk("N9f NaN nội suy trên ramp: sai số ≤ 1 đơn vị",
        err3 <= 1.0 and rep["replaced"] == 2, f"sai số {err3:.3f}")


# ==================================================================== N10 Pdot
def n10_pdot():
    section("N10 — Pdot (Crab): cần bao lâu mới quan trọng")
    import psr_core as C
    P, pdot = 0.0334193, 4.2e-13
    fdot = pdot / P ** 2                                  # Hz/s
    drift6h = 0.5 * fdot * 21600.0 ** 2
    chk("N10a trôi pha 6 h của Crab ≈ 0,03 vòng (đúng bậc độ lớn)",
        0.005 < drift6h < 0.1, f"{drift6h:.4f} vòng")
    T_bad = math.sqrt(0.1 / fdot)
    chk("N10b ngưỡng bỏ qua Pdot (trôi 10 % vòng) ≈ 4–5 giờ",
        12000 < T_bad < 25000, f"T ≈ {T_bad/3600:.1f} giờ")

    # kiểm chứng: fold có Pdot đúng thì SNR cao hơn bỏ qua Pdot (6 h, tsamp 2 ms)
    rng = np.random.default_rng(71)
    ts, T = 2e-3, 21600.0
    n = int(T / ts)
    t = np.arange(n) * ts
    ph = t / P - 0.5 * pdot * t ** 2 / P ** 2
    x = 6.0 * np.exp(-0.5 * ((np.mod(ph, 1.0) - 0.3) / 0.03) ** 2) + rng.normal(0, 1, n)
    s_ok = C.profile_snr(C.fold(x, ts, P, nbins=128, pdot=pdot)[0])[0]
    s_no = C.profile_snr(C.fold(x, ts, P, nbins=128, pdot=0.0)[0])[0]
    chk("N10c dùng Pdot cho SNR cao hơn bỏ qua Pdot (6 h quan sát)",
        s_ok > 1.02 * s_no, f"{s_ok:.1f}σ vs {s_no:.1f}σ "
                            f"(+{100*(s_ok/s_no-1):.1f} %)")


# ============================================================ N11 lượng tử hoá
def n11_quant():
    section("N11 — lượng tử hoá 4-bit vs 8-bit (có ngoại lai 50×)")
    import tempfile, os, shutil
    import psr_sim, psr_fil, psr_core as C
    tmp = tempfile.mkdtemp(prefix="q_")
    try:
        dyn, fr, _ = psr_sim.simulate(dm=26.8, period_s=0.714519, w50_ms=12.0,
                                      nchan=64, bw_mhz=64, tsamp_s=5e-4,
                                      t_total_s=60.0, snr_target=20.0,
                                      rfi=False, seed=81)
        dyn = dyn.astype(np.float32).copy()
        dyn[10, :] *= 50.0                        # RFI mạnh 1 kênh
        keep = np.ones(64, bool)
        keep[10] = False                          # pipeline cũng cắt kênh này
        hdr = dict(source_name="T", nchans=64, nifs=1, nbeams=1, telescope_id=6,
                   machine_id=0, data_type=1, tsamp=5e-4, tstart=60000.0,
                   fch1=float(fr[0]), foff=-1.0)
        snrs = {}
        for nbits in (32, 16, 8, 4):
            p = os.path.join(tmp, f"q{nbits}.fil")
            psr_fil.write_fil(p, dyn, dict(hdr, nbits=nbits))
            _, d = psr_fil.read_fil(p)
            s, _ = C.dedisperse(d[keep], fr[keep], 26.8, 5e-4)
            snrs[nbits] = C.profile_snr(C.fold(s, 5e-4, 0.714519)[0])[0]
        ref = snrs[32]
        for nbits, tol in ((16, 3.0), (8, 12.0), (4, 12.0)):
            num(f"N11a {nbits}-bit so với 32-bit: mất SNR ≤ {tol:g} % "
                f"(có 1 kênh RFI 50×)", (ref - snrs[nbits]) / ref * 100, tol,
                unit=" %", note=f"32-bit {ref:.2f}σ → {nbits}-bit {snrs[nbits]:.2f}σ")
        chk("N11b 4-bit vẫn giữ được xung (SNR > 5σ)", snrs[4] > 5.0,
            f"{snrs[4]:.2f}σ")
        # tệp TỰ KHAI SAI: nbits lạ phải bị từ chối, không ghi ngầm 8-bit
        raised = False
        try:
            psr_fil.write_fil(os.path.join(tmp, "bad.fil"), dyn,
                              dict(hdr, nbits=12))
        except ValueError:
            raised = True
        chk("N11c nbits lạ (12) bị từ chối — không ghi tệp tự khai sai", raised)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ============================================================ N12 cơ số thời gian
def n12_timebase():
    section("N12 — cơ số thời gian")
    ts = 0.000512
    err = abs(float(np.float32(ts)) - ts) / ts
    chk("N12a tsamp 512 µs lưu float32: lệch ≤ 1e-7", err < 1e-7,
        f"{err:.2e} tương đối → {err*18000:.4f} s trên 5 h")
    num("N12b n·tsamp khớp 4 h (≤ 1 s)", 28_125_000 * ts - 14400.0, 1.0, unit=" s")
    counter = np.delete(np.arange(1_000_000, dtype=np.int64), np.s_[500_000:500_003])
    gaps = np.where(np.diff(counter) != 1)[0]
    chk("N12c đếm mẫu phát hiện đúng 1 chỗ mất 3 mẫu", len(gaps) == 1 and
        int(counter[int(gaps[0]) + 1] - counter[int(gaps[0])]) == 4, f"{len(gaps)} chỗ")
    chk("N12d bộ đếm int64 không tràn ở 2,15e9 mẫu",
        int(np.int64(2**31) + 5) == 2147483653)
    chk("N12e Vela trong 4 h ≈ 161 200 chu kỳ", abs(14400.0 / 0.089328 - 161200) < 500,
        f"{14400.0/0.089328:.0f}")


# =================================================== N13 bề rộng hồ sơ / lưới
def n13_width_grid():
    section("N13 — W50/W25 đo trên hồ sơ: BẤT BIẾN theo lưới độ rộng")
    import psr_core as C

    # ---- (a) Gauss giải tích: W50 = 2,35482σ ; W25 = 3,33022σ ; W25/W50 = √2
    ts = 1e-4
    t = np.arange(4000) * ts
    for sig_ms in (0.4, 1.0, 2.5):
        sig = sig_ms * 1e-3
        mw = C.measure_widths(20 * np.exp(-0.5 * ((t - 0.15) / sig) ** 2), ts)
        w50_th, w25_th = 2.35482 * sig_ms, 3.33022 * sig_ms
        num(f"N13a Gauss σ={sig_ms:g} ms: W50 lệch ≤ 2 %",
            (mw["w50_ms"] - w50_th) / w50_th * 100, 2.0, unit=" %",
            note=f"{mw['w50_ms']:.3f} vs {w50_th:.3f} ms")
        num(f"N13b Gauss σ={sig_ms:g} ms: W25 lệch ≤ 2 %",
            (mw["w25_ms"] - w25_th) / w25_th * 100, 2.0, unit=" %",
            note=f"{mw['w25_ms']:.3f} vs {w25_th:.3f} ms")
        num(f"N13c Gauss σ={sig_ms:g} ms: W25/W50 = √2 (≤ 2 %)",
            (mw["w25_ms"] / mw["w50_ms"] - math.sqrt(2)) / math.sqrt(2) * 100,
            2.0, unit=" %")

    # ---- (d) BẤT BIẾN: cùng một xung, ba lưới độ rộng khác nhau.
    # σ = 8 ms → W50 ≈ 19 ms ≈ 38 mẫu: bề rộng tối ưu rơi GIỮA 32 và 64 mẫu,
    # đúng ca bệnh của B0329+54 (lưới thô chọn 32, lưới mịn có 48 chọn 48).
    rng = np.random.default_rng(131)
    P, ts2, T = 0.714519, 5e-4, 120.0
    n = int(T / ts2)
    tt = np.arange(n) * ts2
    sig = 8.0e-3
    x = (25 * np.exp(-0.5 * (((tt % P) - 0.37 * P) / sig) ** 2)
         + rng.normal(0, 1, n))
    grids = {"thô (1,2,4,8,16,32,64)": (1, 2, 4, 8, 16, 32, 64),
             "mịn (…,32,48,64,96)": C.PULSE_WIDTHS,
             "rất mịn (+40,56,80)": (1, 2, 4, 8, 16, 32, 40, 48, 56, 64, 80, 96)}
    got = {}
    for name, grid in grids.items():
        p0 = max(C.find_pulses(x, ts2, threshold=10.0, widths=grid),
                 key=lambda d: d["snr"])
        got[name] = p0
        print(f"     {name:>22}: width_samples={p0['width_samples']:3d} "
              f"({p0['width_ms']:5.2f} ms) | W50={p0['w50_ms']:.3f} ms "
              f"| W25={p0['w25_ms']:.3f} ms | SNR {p0['snr']:.1f}")
    ref = got["mịn (…,32,48,64,96)"]
    for name, p0 in got.items():
        if name.startswith("mịn"):
            continue
        num(f"N13d W25 không phụ thuộc lưới [{name}] (≤ 1 mẫu)",
            abs(p0["w25_ms"] - ref["w25_ms"]) / (ts2 * 1e3), 1.0, unit=" mẫu",
            note=f"W25 {p0['w25_ms']:.3f} vs {ref['w25_ms']:.3f} ms")
        num(f"N13e W50 không phụ thuộc lưới [{name}] (≤ 1 mẫu)",
            abs(p0["w50_ms"] - ref["w50_ms"]) / (ts2 * 1e3), 1.0, unit=" mẫu")
    ws = {k: v["width_samples"] for k, v in got.items()}
    chk("N13f lưới thô/mịn cho width_samples KHÁC nhau (đúng ca bệnh)",
        len(set(ws.values())) > 1, f"width_samples = {ws}")
    chk("N13g dù width_samples khác, W25 vẫn khớp ≤ 1 mẫu",
        abs(got["thô (1,2,4,8,16,32,64)"]["w25_ms"] - ref["w25_ms"]) < ts2 * 1e3,
        f"{got['thô (1,2,4,8,16,32,64)']['w25_ms']:.3f} vs {ref['w25_ms']:.3f} ms")
    for k, p0 in got.items():
        chk(f"N13h W25 ≥ W50 > 0 [{k}]", p0["w25_ms"] >= p0["w50_ms"] > 0,
            f"W50 {p0['w50_ms']:.2f} ≤ W25 {p0['w25_ms']:.2f} ms")
    edge = 20 * np.exp(-0.5 * ((np.arange(20) - 2.0) / 6.0) ** 2)
    mw_e = C.measure_widths(edge, ts, i_peak=2)      # sườn trái bị cắt
    chk("N13i xung sát biên: trả None thay vì bịa bề rộng",
        mw_e["w50_ms"] is None, f"w50 = {mw_e['w50_ms']}")


GROUPS = {"N1": n1_rounding, "N2": n2_fold, "N3": n3_snr, "N4": n4_period,
          "N5": n5_smear, "N6": n6_dmstep, "N7": n7_precision, "N8": n8_stats,
          "N9": n9_degenerate, "N10": n10_pdot, "N11": n11_quant,
          "N12": n12_timebase, "N13": n13_width_grid}


def main(argv):
    sel = [a.upper() for a in argv[1:] if not a.startswith("-")]
    t0 = time.time()
    for k, fn in GROUPS.items():
        if sel and k not in sel:
            continue
        try:
            fn()
        except Exception as exc:                 # noqa: BLE001
            import traceback
            traceback.print_exc()
            chk(f"{k}: chạy không lỗi", False, repr(exc))
    print("\n" + "=" * 76)
    per = {}
    for g, name, ok, _ in RES:
        per.setdefault(g, [0, 0])
        per[g][0] += int(ok)
        per[g][1] += 1
    for g, (ok, tot) in per.items():
        print(f"  {g:>4}: {ok:>2}/{tot:<2} {'PASS' if ok == tot else 'FAIL'}")
    n_ok = sum(int(r[2]) for r in RES)
    print(f"\nTỔNG: {n_ok}/{len(RES)} · {time.time()-t0:.1f}s")
    fails = [(g, n, d) for g, n, ok, d in RES if not ok]
    if fails:
        print("\nKHÔNG ĐẠT:")
        for g, n, d in fails:
            print(f"  ✗ [{g}] {n} — {d}")
    return 0 if not fails else 1


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                            # noqa: BLE001
        pass
    sys.exit(main(sys.argv))
