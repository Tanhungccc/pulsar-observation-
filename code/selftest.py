# -*- coding: utf-8 -*-
"""
selftest.py — Kiểm chứng máy móc toàn bộ lõi thuật toán (chạy trước mỗi lần
sửa code, và trước khi tin bất kỳ con số nào trong tài liệu).

    python selftest.py            # ~30–60 s
    python selftest.py --fast     # bỏ phần pipeline đầy đủ

Mỗi test in PASS/FAIL kèm con số đo được; exit code 1 nếu có FAIL.
"""
from __future__ import annotations

import sys

import numpy as np

from psr_core import (band_smear_ms, dedisperse, dm_delay_s, dm_from_subbands,
                      ensure_utf8_stdout, find_pulses, fold, profile_snr,
                      refine_period, subband_dm_single, zero_dm_excise)
from psr_sensitivity import Dish, chan_smear_ms, snr_fold
from psr_sim import simulate
from psr_targets import alt_max

RESULT = []


def check(name, ok, detail=""):
    RESULT.append(ok)
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f"  — {detail}" if detail else ""))


def test_physics():
    d = Dish()
    check("A_eff 3.7 m, eta 0.55 ≈ 5.91 m²", abs(d.aeff_m2 - 5.91) < 0.05,
          f"{d.aeff_m2:.3f} m²")
    g = d.gain_kjy() * 1e3
    check("G ≈ 2.14 mK/Jy", abs(g - 2.14) < 0.02, f"{g:.3f} mK/Jy")
    sefd = d.sefd_jy(150)
    check("SEFD(150 K) ≈ 70 kJy", abs(sefd / 1e3 - 70.0) < 2.0,
          f"{sefd/1e3:.1f} kJy")
    check("Beam @1420 MHz ≈ 4.0°", abs(d.beam_deg(1420) - 3.99) < 0.1,
          f"{d.beam_deg(1420):.2f}°")
    # trễ tuyệt đối tới tần số vô cực: DM 26.8 @1400 MHz = 56.7 ms
    t_abs = float(dm_delay_s(26.8, 1400.0)) * 1e3
    check("Trễ tuyệt đối DM 26.8 @1400 MHz ≈ 56.7 ms", abs(t_abs - 56.7) < 0.3,
          f"{t_abs:.2f} ms")
    # trải trong dải 2 MHz quanh 1400 MHz ≈ 0.16 ms (khớp PROJECT_PLAN §3.2)
    sm = band_smear_ms(26.8, 1399.0, 1401.0)
    check("Trải DM 26.8 trên dải 2 MHz ≈ 0.16 ms", abs(sm - 0.162) < 0.01,
          f"{sm:.3f} ms")
    # trải một kênh phải nhỏ hơn trải cả dải
    check("trải/kênh < trải/dải",
          chan_smear_ms(100, 1400, 1.0) < band_smear_ms(100, 1368, 1432))


def test_dedispersion():
    """Bơm một xung tại thời điểm biết trước, kiểm tra khử tán sắc đặt đúng chỗ."""
    nchan, bw, fc, ts = 64, 64.0, 1400.0, 2.5e-4
    freqs = fc + (np.arange(nchan) - (nchan - 1) / 2) * bw / nchan
    ntime = 40000
    dm = 150.0
    dyn = np.zeros((nchan, ntime))
    t0 = 2.0
    for i in range(nchan):
        c = t0 + 4.148808e3 * dm * (1 / freqs[i]**2 - 1 / freqs.max()**2)
        j = int(round(c / ts))
        if 0 <= j < ntime:
            dyn[i, j] = 100.0
    # Trục thời gian của chuỗi SAU khử tán sắc là thời gian PHÁT XẠ ≈ j·ts
    # (mọi kênh đã được đưa về cùng mốc phát xạ), không phải (j+shift)·ts.
    for chk_dm, should in ((dm, True), (dm + 400, False)):
        s, sh = dedisperse(dyn, freqs, chk_dm, ts)
        k = int(np.argmax(s))
        t_peak = k * ts
        ok = (abs(t_peak - t0) < 3 * ts) if should else (abs(t_peak - t0) > 20 * ts)
        check(f"khử tán sắc DM={chk_dm:.0f} → xung {'đúng chỗ' if should else 'lệch chỗ'}",
              ok, f"đỉnh tại {t_peak:.4f} s (đặt {t0} s), còn {s.max():.0f}/63")


def test_snr_calibration():
    """SNR đặt trong mô phỏng phải khớp SNR đo được sau fold (sai < 20%)."""
    P = 0.089328
    dyn, f, m = simulate(dm=67.94, period_s=P, w50_ms=3.0, rfi=False,
                         t_total_s=60.0, snr_target=25.0, tsamp_s=5e-4,
                         nchan=64, bw_mhz=64.0, seed=3)
    s, _ = dedisperse(dyn, f, 67.94, m["tsamp_s"])
    prof, _ = fold(s, m["tsamp_s"], P, nbins=256)
    snr = profile_snr(prof)[0]
    check("SNR mô phỏng khớp SNR fold", abs(snr / 25.0 - 1) < 0.25,
          f"đặt 25.0, đo {snr:.1f}")


def test_sensitivity_formula():
    """Công thức SNR_fold phải tái tạo được kết quả mô phỏng cùng điều kiện."""
    dish = Dish()
    sefd = dish.sefd_jy(150)
    s_mean = 2.5           # Jy — phải ĐỦ MẠNH: ở SNR thấp, max của lọc khớp
                           # bị thiên lệch dương ~3σ nên không so sánh được
    P, W = 0.089328, 0.003
    pred = snr_fold(s_mean, sefd, 64e6, 60.0, P, W)
    dyn, f, m = simulate(dm=67.94, period_s=P, w50_ms=W * 1e3, rfi=False,
                         t_total_s=60.0, snr_target=pred, tsamp_s=5e-4,
                         nchan=64, bw_mhz=64.0, seed=4)
    s, _ = dedisperse(dyn, f, 67.94, m["tsamp_s"])
    prof, _ = fold(s, m["tsamp_s"], P, nbins=256)
    meas = profile_snr(prof)[0]
    check("Ngân sách S/N ↔ mô phỏng nhất quán", abs(meas / pred - 1) < 0.25,
          f"công thức {pred:.1f} vs mô phỏng {meas:.1f}")
    # và: dữ liệu CHỈ CÓ NHIỄU vẫn cho SNR ~3 (thiên lệch max) → không phải phát hiện
    dyn0, f0_, m0 = simulate(dm=0.0, period_s=P, w50_ms=W * 1e3, rfi=False,
                             t_total_s=60.0, snr_target=0.0, tsamp_s=5e-4,
                             nchan=64, bw_mhz=64.0, seed=8)
    s0, _ = dedisperse(dyn0, f0_, 0.0, m0["tsamp_s"])
    pr0, _ = fold(s0, m0["tsamp_s"], P, nbins=256)
    snr0 = profile_snr(pr0)[0]
    check("Nhiễu thuần cho SNR ~3 (biết để không nhận nhầm)", snr0 < 5.5,
          f"{snr0:.1f}σ — ngưỡng phát hiện phải ≥ 6–8")


def test_period_refine():
    """Tinh chỉnh chu kỳ phải đạt sai số < 100 ppm từ một P0 lệch 0.4%."""
    P = 0.714519
    dyn, f, m = simulate(dm=67.94, period_s=P, w50_ms=6.0, rfi=False,
                         t_total_s=60.0, snr_target=40.0, tsamp_s=5e-4,
                         nchan=32, bw_mhz=64.0, seed=9)
    s, _ = dedisperse(dyn, f, 67.94, m["tsamp_s"])
    P0 = P * 1.004
    Pr, snr, _ = refine_period(s, m["tsamp_s"], P0, iters=3)
    ppm = abs(Pr - P) / P * 1e6
    check("Tinh chỉnh chu kỳ < 100 ppm", ppm < 100, f"{ppm:.1f} ppm, SNR {snr:.1f}")


def test_subband_dm():
    dyn, f, m = simulate(dm=200.0, period_s=0.089328, w50_ms=3.0, rfi=False,
                         t_total_s=60.0, snr_target=80.0, tsamp_s=5e-4,
                         nchan=64, bw_mhz=64.0, seed=6)
    r = dm_from_subbands(dyn, f, m["tsamp_s"], 0.089328, nsub=4)
    err = abs(r["dm"] / 200.0 - 1)
    check("DM dải con sai < 8%", err < 0.08,
          f"DM {r['dm']:.1f} vs 200.0 ({err*100:.1f}%)")


def test_constants():
    """L0: hằng số vật lý + công thức dẫn xuất (chống lỗi đơn vị)."""
    import psr_constants as C
    bad = C.self_check()
    check("hằng số & công thức chuẩn (K_DM, nhòe kênh, HPBW, SEFD, tán xạ)",
          not bad, "; ".join(bad) or f"K_DM={C.K_DM:g}")


def test_site_profile():
    """L0: hồ sơ trạm/kính — số mặc định, đổi trạm, nam bán cầu, chia kênh."""
    import psr_site as S
    bad = S.self_check()
    check("hồ sơ mặc định cho lại số đã công bố (HPBW/SEFD)", not bad, "; ".join(bad))

    # đổi sang trạm nam bán cầu: không được giả định bắc bán cầu
    p = S.default_profile()
    p.site = S.Site("Sydney", -33.87, 151.21, 40, 10)
    alt_neg = 90.0 - abs(p.site.lat_deg - (-45.0))
    check("hồ sơ nam bán cầu: alt_max tính đúng",
       abs(alt_neg - 78.87) < 0.5, f"alt_max={alt_neg:.1f}°")

    # kính nhỏ hơn: SEFD phải tăng theo 1/A
    small = S.Telescope("1.4 m", 1.4, 0.55)
    big = S.Telescope("3.7 m", 3.7, 0.55)
    b = S.Band("x", 1420.0, 20.0, 150.0)
    ratio = b.sefd_jy(small) / b.sefd_jy(big)
    check("SEFD ∝ 1/A khi đổi kính", abs(ratio - (3.7 / 1.4) ** 2) < 0.5,
       f"tỷ số {ratio:.2f}, cần {(3.7/1.4)**2:.2f}")

    # cảnh báo chia kênh
    chk = S.default_profile().check_channelization(S.Band("x", 423.0, 20.0), 64, 50.0, 2.0)
    check("cảnh báo khi nhòe kênh > W50/2", not chk["ok"], chk["advice"][:60])


def test_ingest_guard():
    """L1: 4 quy tắc I/O + nhận dạng mù (docs/07 §6c)."""
    import ingest_guard as G
    bad = G.self_check()
    check("ingest_guard: nhận dạng mù + 4 quy tắc I/O", not bad, "; ".join(bad))

    import os as _os, tempfile
    NL = chr(10)
    tmp = tempfile.mkdtemp(prefix="ig_")
    p = _os.path.join(tmp, "rtcs_export.csv")
    hdr = "time_s," + ",".join("ch" + str(i) for i in range(64))
    with open(p, "w", encoding="utf-8") as fh:
        fh.write("# RTCS v2 export pho dong" + NL)
        fh.write("# freq 1400 MHz, 64 kenh" + NL)
        fh.write(hdr + NL)
        for i in range(400):
            vals = ",".join("%.4f" % (1 + 0.01 * np.sin(i / 10 + j)) for j in range(64))
            fh.write(("%.4f" % (i * 0.001)) + "," + vals + NL)
    import psr_detect
    m = psr_detect.detect(p, dm_max=5.0)
    check("CSV 2D của back-end (bỏ header text) đọc + phân tích được",
          m.get("status") in ("ok", "rfi_zero_dm"),
          "status=%s guard=%s" % (m.get("status"), (m.get("guard") or {}).get("tags")))
    check("report có input_sha256 + schema_version",
          bool(m.get("input_sha256")) and m.get("schema_version") == 3,
          "sha=%s" % str(m.get("input_sha256"))[:10])

def test_dm_max_auto():
    """A8: dm_max tự mở rộng theo dm_ref (Vela 68, B1641-45 479)."""
    import psr_detect, io as _io, contextlib as _ctx, tempfile as _tf
    okall = True
    detail = []
    for ref, need in ((None, 100.0), (67.94, 101.9), (478.7, 718.0)):
        _old = psr_detect.RESULTS
        psr_detect.RESULTS = _tf.mkdtemp(prefix="dmmax_")
        try:
            with _ctx.redirect_stdout(_io.StringIO()):
                m = psr_detect.detect("../data/stress/28.fil", dm_ref=ref)
            got = float(m["stage"].get("dm_max") or 0)
        finally:
            psr_detect.RESULTS = _old
        good = got >= need - 1.0
        okall = okall and good
        detail.append(f"ref={ref}→{got:.0f}")
    check("dm_max tự mở rộng theo dm_ref (không quét thiếu Vela/B1641-45)",
          okall, ", ".join(detail))


def test_blind_period():
    """M3: dò chu kỳ mù (FFT + sàng hài + ưu tiên chu kỳ cơ bản)."""
    import psr_sim, psr_core, psr_period
    dyn, freqs, meta = psr_sim.simulate(dm=3.0, period_s=0.100, w50_ms=6.0,
                                        nchan=64, bw_mhz=32.0, tsamp_s=256e-6,
                                        t_total_s=120.0, snr_target=40.0,
                                        rfi=False, seed=5)
    s, _ = psr_core.dedisperse(dyn, freqs, 3.0, 256e-6)
    res = psr_period.blind_period_search(s, 256e-6, top=8, threshold=8.0)
    best = res.get("best") or {}
    p_got = float(best.get("p_s") or 0.0)
    err = abs(p_got - 0.100) / 0.100 if p_got else 1.0
    check("M3 dò chu kỳ mù tìm đúng P (sai số < 0.1 %)",
          err < 1e-3 and "best" in res,
          f"P = {p_got*1e3:.3f} ms (thật 100 ms), SNR {best.get('snr')}")
    check("M3 ưu tiên chu kỳ CƠ BẢN (không báo P/2 hay 2P)",
          p_got and abs(p_got / 0.100 - 1.0) < 1e-3,
          f"tỷ số P/P_true = {p_got / 0.100:.6f}" if p_got else "—")
    check("M3 loại hài: số ứng viên sau sàng < trước sàng",
          res.get("n_after_sift", 99) <= res.get("n_fft_candidates", 0),
          f"{res.get('n_fft_candidates')} → {res.get('n_after_sift')}")


def test_i18n():
    """L6: đa ngôn ngữ — dịch, fallback, lưu/đọc settings."""
    import psr_i18n as L
    bad = L.self_check()
    check("i18n: dịch vi↔en + fallback giữ nguyên chuỗi lạ", not bad, "; ".join(bad))
    cov = L.coverage()
    check("i18n: đã dịch đủ bộ nhãn giao diện (≥ 60 chuỗi)",
          cov["n_translated"] >= 60, f"{cov['n_translated']} chuỗi")


def test_targets():
    a = alt_max(7.9266)      # B0950+08
    check("alt_max(B0950+08) ≈ 87.1°", abs(a - 87.1) < 0.2, f"{a:.1f}°")


def test_zero_dm_keeps_pulse():
    """zero-DM phải cắt RFI băng rộng nhưng KHÔNG được cắt xung tán sắc."""
    nchan, ntime = 64, 4000
    rng = np.random.default_rng(5)
    dyn = rng.normal(1, 1, (nchan, ntime))
    # RFI băng rộng: 20 mẫu vượt ngưỡng trên MỌI kênh
    dyn[:, 1000:1003] += 30
    dyn[:, 2500:2502] += 25
    # xung tán sắc: dải quét qua 200 mẫu (chỉ ~10% kênh mỗi thời điểm)
    for i in range(nchan):
        j = 3000 + int(i * 200 / nchan)
        dyn[i, j:j + 4] += 20
    out, bad = zero_dm_excise(dyn, threshold=6.0)
    cut_rfi = bad[1000:1003].all() and bad[2500:2502].all()
    cut_pulse = bad[3000:3200].any()
    check("zero-DM cắt được RFI băng rộng", bool(cut_rfi),
          f"{bad.sum()} mẫu bị cắt")
    check("zero-DM GIỮ được xung tán sắc", not bool(cut_pulse),
          f"mẫu xung bị cắt: {int(bad[3000:3200].sum())}")


def test_subband_dm_single():
    """Đo DM từ 1 xung đơn phải chính xác vài % khi SNR tốt."""
    dyn, f, m = simulate(dm=200.0, period_s=2.0, w50_ms=3.0, rfi=False,
                         t_total_s=4.0, snr_target=200.0, tsamp_s=2.5e-4,
                         nchan=64, bw_mhz=64.0, f_center_mhz=1400.0, seed=21)
    r = subband_dm_single(dyn, f, m["tsamp_s"], 2.0, window_s=0.05, nsub=8,
                          dm_guess=195.0, width_samples=8)
    err = abs(r["dm"] / 200.0 - 1)
    check("DM xung đơn (dải con) sai < 8%", err < 0.08,
          f"DM {r['dm']:.1f} vs 200.0 ({err*100:.1f}%)")
    # và: gọi sai thời điểm (không có xung) phải BÁO LỖI, không trả DM rác
    try:
        subband_dm_single(dyn, f, m["tsamp_s"], 1.0, window_s=0.05, nsub=8,
                          dm_guess=195.0, width_samples=8)
        check("gọi sai thời điểm phải báo lỗi", False, "trả về DM rác")
    except ValueError:
        check("gọi sai thời điểm phải báo lỗi", True, "đã raise ValueError")


def test_find_pulses_cluster():
    """Tìm xung: đúng số lượng, gom cụm không đếm trùng."""
    ts = 1e-3
    x = np.random.default_rng(4).normal(0, 1, 5000)
    x[1000:1006] += 12
    x[1002:1004] += 8          # đỉnh phụ sát xung 1 — không được tách đôi
    x[3000:3006] += 12
    p = find_pulses(x, ts, threshold=8.0, widths=(2, 4), min_sep_s=0.05)
    check("gom cụm xung: đúng 2 xung", len(p) == 2,
          f"t = {[round(q['t_s'],3) for q in p]}")


def test_iq_channelize():
    """IQ thô → channelize: phải đặt đúng tần số và bỏ được méo IQ."""
    import tempfile, os
    from psr_iq import write_sigmf, read_iq_as_dyn
    fs, fc, n = 2.4e6, 1420e6, 200_000
    rng = np.random.default_rng(11)
    t = np.arange(n) / fs
    iq = (rng.normal(0, 1, n) + 1j * rng.normal(0, 1, n)) * 0.5
    iq += np.exp(2j * np.pi * 12e3 * t) * 3 + (2 + 1j)   # tín hiệu + DC
    iq = iq.real * 1.15 + 1j * iq.imag                    # mất cân bằng biên độ
    stem = os.path.join(tempfile.gettempdir(), "_iq_selftest")
    write_sigmf(stem, iq, fs, fc, "ci16_le")
    h, dyn = read_iq_as_dyn(stem + ".sigmf-data", nchan=64)
    k = int(np.argmax(dyn.mean(axis=1)))
    err_mhz = abs(h["freqs_mhz"][k] - (fc + 12e3) / 1e6)
    amp = h["iq_fix"]["iq_amplitude_ratio"]
    ok = 0.05 < dyn.shape[1] and err_mhz < 0.05 and 1.05 < amp < 1.25
    check("IQ: đọc + channelize đúng tần số, phát hiện méo IQ", ok,
          f"đỉnh {h['freqs_mhz'][k]:.4f} MHz (lệch {err_mhz*1e3:.1f} kHz), "
          f"tỉ số I/Q đo {amp:.2f}")
    for f in (stem + ".sigmf-data", stem + ".sigmf-meta"):
        if os.path.exists(f):
            os.unlink(f)


def test_fil_roundtrip():
    """Ghi/đọc .fil phải giữ nguyên dữ liệu + header."""
    from psr_fil import write_fil, read_fil
    import tempfile, os
    rng = np.random.default_rng(6)
    dyn = rng.integers(0, 200, (32, 500)).astype(np.uint8)
    fd, path = tempfile.mkstemp(suffix=".fil"); os.close(fd)
    write_fil(path, dyn, dict(source_name="SELFTEST", nbits=8, nchans=32,
                              tsamp=2.5e-4, tstart=60000.0, fch1=1420.0,
                              foff=-0.1))
    h, d2 = read_fil(path, validate=True)
    ok = (h["nchans"] == 32 and d2.shape == (32, 500)
          and np.array_equal(d2, dyn.astype(np.float32)))
    os.unlink(path)
    check("fil write→read round-trip", ok,
          f"{d2.shape}, tsamp {h['tsamp_s']}")


def test_pipeline():
    from psr_pipeline import run
    m = run(quick=True)
    ok = (abs(m["dm_subband"] / m["dm_true"] - 1) < 0.10
          and abs(m["period_err_ppm"]) < 300
          and m["snr_fold_refined"] > 10)
    check("Pipeline end-to-end (quick)",
          ok, f"DM {m['dm_subband']:.1f}/{m['dm_true']}, "
              f"P lệch {m['period_err_ppm']:+.0f} ppm, "
              f"SNR {m['snr_fold_refined']:.1f}")


if __name__ == "__main__":
    ensure_utf8_stdout()
    fast = "--fast" in sys.argv
    print(f"Python {sys.version.split()[0]} | numpy {np.__version__}\n")
    test_physics()
    test_dedispersion()
    test_snr_calibration()
    test_sensitivity_formula()
    test_period_refine()
    test_subband_dm()
    test_constants()
    test_ingest_guard()
    test_dm_max_auto()
    test_blind_period()
    test_i18n()
    test_site_profile()
    test_targets()
    test_zero_dm_keeps_pulse()
    test_subband_dm_single()
    test_find_pulses_cluster()
    test_fil_roundtrip()
    test_iq_channelize()
    if not fast:
        test_pipeline()
    n_ok = sum(RESULT)
    print(f"\n{n_ok}/{len(RESULT)} test PASS")
    sys.exit(0 if n_ok == len(RESULT) else 1)
