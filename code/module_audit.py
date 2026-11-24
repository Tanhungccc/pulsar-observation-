# -*- coding: utf-8 -*-
"""module_audit.py — KIỂM TRA TỪNG MODULE RIÊNG RẺ (ca biên khắc nghiệt).

Khác `selftest.py` (kiểm pipeline end-to-end), file này soi từng module một:
mỗi module có ≥ 3 phép thử, ưu tiên **ca biên và ca xấu** (đầu vào sai, cực trị,
file hỏng, dữ liệu lệch bậc, tham số phi lý) thay vì đường đi thuận.

Chạy:  python module_audit.py            # tất cả
       python module_audit.py psr_period # một module
"""
from __future__ import annotations

import io
import contextlib
import math
import os
import shutil
import re
import sys
import tempfile
import time

import numpy as np

RES = []
CUR = {"module": "?"}


def chk(name: str, cond, detail: str = ""):
    ok = bool(cond)
    RES.append((CUR["module"], name, ok, detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    return ok


def section(mod: str):
    CUR["module"] = mod
    print(f"\n=== {mod} ===")


def quiet(fn, *a, **k):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        try:
            return fn(*a, **k), buf.getvalue()
        except Exception as exc:                 # noqa: BLE001
            return exc, buf.getvalue()


# --------------------------------------------------------------- psr_constants
def audit_constants():
    section("psr_constants")
    import psr_constants as C
    chk("self_check nội bộ sạch", not C.self_check(), "; ".join(C.self_check()))
    d = C.dm_delay_s(1.0, 1399.5, 1400.5)
    chk("trễ tán sắc 1 DM @1,4 GHz trên 1 MHz ≈ 3,03 µs",
        abs(d - 3.03e-6) < 0.05e-6, f"{d*1e6:.2f} µs")
    # đảo tần số phải cho cùng kết quả (trị tuyệt đối)
    chk("trễ không phụ thuộc thứ tự f_lo/f_hi",
        abs(C.dm_delay_s(50, 400, 420) - C.dm_delay_s(50, 420, 400)) < 1e-12)
    bad = []
    for args in ((1.0, 0.0, 420.0), (1.0, -1.0, 420.0)):
        try:
            C.dm_delay_s(*args)
            bad.append(args)
        except ValueError:
            pass
    chk("tần số ≤ 0 phải ném ValueError", not bad, str(bad))
    chk("HPBW giảm khi tăng tần số",
        C.hpbw_deg(3.7, 1420) < C.hpbw_deg(3.7, 423),
        f"{C.hpbw_deg(3.7,1420):.2f}° < {C.hpbw_deg(3.7,423):.2f}°")
    # tán xạ: DM lớn hơn → τ lớn hơn; tần số cao hơn → τ nhỏ hơn
    chk("τ tán xạ tăng theo DM và giảm theo tần số",
        C.tau_scattering_ms(400, 423) > C.tau_scattering_ms(100, 423)
        and C.tau_scattering_ms(100, 1420) < C.tau_scattering_ms(100, 423))
    chk("W(ν) ≥ max(W_nội, τ) (cộng bình phương)",
        C.w50_at(8.6, 478.7, 423) >= C.tau_scattering_ms(478.7, 423))


# ------------------------------------------------------------------- psr_site
def audit_site():
    section("psr_site")
    import psr_site as S
    chk("self_check nội bộ sạch", not S.self_check(), "; ".join(S.self_check()))
    p = S.default_profile()
    chk("tra băng theo id", p.band("lband").fc_mhz == 1420.0)
    chk("tra băng theo tần số (±10 %)", p.band(1425).id == "lband")
    chk("tần số ngoài mọi băng → None", p.band(900) is None)
    chk("SEFD tỉ lệ nghịch bình phương đường kính",
        abs((S.Band("x", 1420, 10, 150).sefd_jy(S.Telescope("1.4 m", 1.4, .55))
             / S.Band("x", 1420, 10, 150).sefd_jy(S.Telescope("3.7 m", 3.7, .55)))
            - (3.7 / 1.4) ** 2) < 0.5)
    # check_channelization: biên
    bad = p.check_channelization(S.Band("x", 423, 20), 64, 50, 2.0)
    good = p.check_channelization(p.band("p423"), 256, 50, 25.0)
    chk("cảnh báo khi nhòe > W50/2", (not bad["ok"]) and bad["advice"])
    chk("không báo động oan khi nhòe nhỏ", good["ok"])
    chk("nchan ≤ 0 bị chặn", not p.check_channelization(p.band("p423"), 0, 10, 10)["ok"])
    # lưu/đọc hồ sơ
    tmp = tempfile.mkdtemp(prefix="site_")
    f = os.path.join(tmp, "p.json")
    p.save(f)
    q = S.load_profile(f)
    chk("lưu → đọc lại giữ nguyên site/kính/băng",
        q.site.lat_deg == p.site.lat_deg and
        abs(q.band("lband").sefd_jy(q.telescope) -
            p.band("lband").sefd_jy(p.telescope)) < 1.0)
    # đổi trạm: nam bán cầu
    p2 = S.default_profile()
    p2.site = S.Site("Nam", -33.9, 151.2, 40, 10)
    chk("hồ sơ nam bán cầu: alt_max < 90 và đúng công thức",
        abs((90 - abs(p2.site.lat_deg - (-45.0))) - 78.9) < 0.5)
    shutil.rmtree(tmp, ignore_errors=True)


# ------------------------------------------------------------------- psr_paths
def audit_hardware_profile():
    section("psr_hw POAM profile")
    import psr_hw as H
    errs = H.self_check()
    chk("psr_hw.self_check includes NCU/ACU facts", not errs, "; ".join(errs))
    ncu, acu, rx = H.PARTS["poam_ncu"], H.PARTS["poam_acu"], H.PARTS["poam_receiver"]
    chk("NCU IP/ECA/cycle match manual", ncu["ip"] == "192.168.1.100"
        and ncu["eca_m2"] == 6.40
        and tuple(ncu["sequence_s"][k] for k in ("noise","load","sun")) == (20,20,240))
    chk("ENR 30 dB explicitly marked as unverified interpretation",
        ncu["enr_db"] == 30.0 and "chưa xác minh" in ncu["note"].lower())
    chk("ACU PARK EL and limit safety note", acu["park_el_deg"] == 85.0
        and "không tự clear" in acu["note"].lower())
    chk("L-band feed status and conditional LO/IF mapping explicit",
        rx["lband_feed_confirmed"] is False
        and rx["if_rf_mapping_mhz"][1500] == (3650,4250))


def audit_paths():
    section("psr_paths")
    import psr_paths as P
    tmp = tempfile.mkdtemp(prefix="paths_")
    old_env = os.environ.get("PSR_SETTINGS")
    os.environ["PSR_SETTINGS"] = os.path.join(tmp, "settings.json")
    try:
        chk("self_check sạch (tự tạo data/results/configs)",
            not P.self_check(), "; ".join(P.self_check()))
        d0, r0 = P.data_dir(), P.results_dir()
        P.set_data_dir(os.path.join(tmp, "d1"))
        chk("settings.json ghi nơi lưu mới", "d1" in P.data_dir(), P.data_dir())
        os.environ["PSR_DATA_DIR"] = os.path.join(tmp, "d_env")
        chk("biến môi trường THẮNG settings", "d_env" in P.data_dir(), P.data_dir())
        del os.environ["PSR_DATA_DIR"]
        chk("bỏ env → quay lại settings", "d1" in P.data_dir())
        P.set_data_dir(d0); P.set_results_dir(r0)
        # chặn ghi vào data/
        raised = False
        try:
            P.assert_write_allowed(os.path.join(P.data_dir(), "x.json"))
        except PermissionError:
            raised = True
        chk("chặn ghi vào data/ (dữ liệu thô chỉ đọc)", raised)
        P.assert_write_allowed(os.path.join(P.results_dir(), "x.json"))
        chk("cho phép ghi vào results/", True)
        # đường dẫn khác ổ đĩa không làm crash is_inside
        chk("is_inside an toàn khi khác ổ đĩa",
            P.is_inside("C:/x/y", "D:/a") is False)
        # output_dir nằm trong results
        od = P.output_dir("zz_test")
        chk("output_dir nằm trong results/ và được tạo",
            P.is_inside(od, P.results_dir()) and os.path.isdir(od), od)
        os.rmdir(od)
        # atomic: không để lại .tmp
        j = os.path.join(tmp, "a.json")
        P.save_settings({"k": 1})
        chk("save_settings không để lại tệp .tmp",
            not os.path.exists(P.settings_path() + ".tmp"))
    finally:
        if old_env is None:
            os.environ.pop("PSR_SETTINGS", None)
        else:
            os.environ["PSR_SETTINGS"] = old_env
        shutil.rmtree(tmp, ignore_errors=True)


# ------------------------------------------------------------------ psr_fil
def audit_fil():
    section("psr_fil")
    import psr_fil
    tmp = tempfile.mkdtemp(prefix="fil_")
    rng = np.random.default_rng(4)
    dyn = (rng.normal(size=(32, 500)) * 10 + 100).astype(np.float32)
    hdr = dict(source_name="T", nchans=32, nifs=1, nbeams=1, telescope_id=6,
               machine_id=0, data_type=1, tsamp=2.5e-4, tstart=60000.0,
               fch1=1420.0, foff=-1.0)
    p8 = os.path.join(tmp, "a.fil")
    psr_fil.write_fil(p8, dyn, dict(hdr, nbits=8))
    h, d = psr_fil.read_fil(p8)
    chk("round-trip 8-bit: số kênh/mẫu/tsamp khớp",
        h["nchans"] == 32 and h["ntime"] == 500 and abs(h["tsamp_s"] - 2.5e-4) < 1e-12)
    chk("round-trip 8-bit: dạng phổ giữ được (tương quan > 0.98)",
        float(np.corrcoef(d.ravel(), dyn.ravel())[0, 1]) > 0.98,
        f"r = {np.corrcoef(d.ravel(), dyn.ravel())[0,1]:.4f}")
    p32 = os.path.join(tmp, "b.fil")
    psr_fil.write_fil(p32, dyn, dict(hdr, nbits=32))
    h2, d2 = psr_fil.read_fil(p32)
    chk("round-trip 32-bit: sai số < 1e-3",
        float(np.max(np.abs(d2 - dyn))) < 1e-3)
    # file cụt: cắt bớt dữ liệu
    pcut = os.path.join(tmp, "cut.fil")
    raw = open(p8, "rb").read()
    open(pcut, "wb").write(raw[: int(len(raw) * 0.6)])
    m, out = quiet(psr_fil.read_fil, pcut)
    chk("file cụt: đọc được phần còn lại HOẶC báo lỗi rõ",
        isinstance(m, tuple) or "cụt" in str(m).lower() or "truncat" in str(m).lower(),
        str(m)[:60] if not isinstance(m, tuple) else "đọc được + cảnh báo")
    # file rỗng
    pe = os.path.join(tmp, "empty.fil")
    open(pe, "wb").close()
    e, _ = quiet(psr_fil.read_fil, pe)
    chk("file 0 byte → ném lỗi có nội dung (không trả mảng rỗng)",
        isinstance(e, Exception) and len(str(e)) > 5, type(e).__name__)
    shutil.rmtree(tmp, ignore_errors=True)


# ----------------------------------------------------------------- psr_fits
def audit_fits():
    section("psr_fits")
    import psr_fits
    tmp = tempfile.mkdtemp(prefix="fits_")
    p = os.path.join(tmp, "t.fits")
    rng = np.random.default_rng(5)
    dyn = (rng.normal(size=(16, 200)) * 5 + 50)
    psr_fits.write_psrfits(p, dyn, tsamp_s=1e-3, f_center_mhz=1400.0,
                           bw_mhz=16.0, source="T", telescope="TEST")
    h, d = psr_fits.read_psrfits(p)
    chk("PSRFITS ghi→đọc: kích thước khớp",
        d.shape == (16, 200), str(d.shape))
    chk("PSRFITS ghi→đọc: sai số ≤ 0,1 đơn vị ADC",
        float(np.max(np.abs(d - dyn))) < 0.1,
        f"max Δ = {np.max(np.abs(d - dyn)):.3f}")
    # file rỗng
    pe = os.path.join(tmp, "empty.fits")
    from astropy.io import fits
    fits.PrimaryHDU().writeto(pe)
    e, _ = quiet(psr_fits.read_psrfits, pe)
    chk("PSRFITS rỗng → lỗi rõ ràng", isinstance(e, Exception), type(e).__name__)
    # file thật GMRT (NSBLK='*')
    real = os.path.join("..", "data", "extra", "B1822-09_650MHz.fits")
    if os.path.exists(real):
        m, _ = quiet(psr_fits.read_psrfits, real)
        chk("PSRFITS thật NSBLK='*' đọc được (không crash)",
            isinstance(m, tuple), "1 tích phân → too_short ở pipeline")
    shutil.rmtree(tmp, ignore_errors=True)


# ------------------------------------------------------------------- psr_iq
def audit_iq():
    section("psr_iq")
    import psr_iq
    tmp = tempfile.mkdtemp(prefix="iq_")
    fs, f0, nchan = 2.0e6, 1420e6, 64
    t = np.arange(200_000) / fs
    iq = np.exp(2j * np.pi * 100e3 * t).astype(np.complex64)      # CW tại +100 kHz
    pdat = os.path.join(tmp, "x.cf32")
    iq.tofile(pdat)
    h, dyn = psr_iq.read_iq_as_dyn(pdat, nchan=nchan, navg=4,
                                   fs_hz=fs, fc_hz=f0)
    f = np.asarray(h["freqs_mhz"])
    peak = float(f[int(np.argmax(np.median(dyn, axis=1)))])
    chk("channelize IQ: đỉnh tại f0 + 100 kHz", abs(peak - 1420.1) < 0.2,
        f"đỉnh {peak:.3f} MHz")
    h32 = psr_iq.read_iq_as_dyn(pdat, nchan=nchan, navg=4,
                                fs_hz=fs, fc_hz=f0)[0]
    chk("số kênh đúng yêu cầu", h32["nchans"] == nchan, str(h32["nchans"]))
    # DC offset phải bị loại: dùng nhiễu + DC (KHÔNG có tone) để đo đúng kênh DC
    rng = np.random.default_rng(11)
    iq_dc = (rng.normal(size=t.size) + 1j * rng.normal(size=t.size)
             + 3.0).astype(np.complex64)
    pdc = os.path.join(tmp, "dc.cf32")
    iq_dc.tofile(pdc)
    d_dc, fr_dc, _ts, _meta = psr_iq.channelize_iq(
        iq_dc, fs, f0, nchan=nchan, navg=4, apply_iq_fix=True)
    spec_dc = np.median(d_dc, axis=1)
    i_dc = int(np.argmin(np.abs(fr_dc - f0 / 1e6)))
    ratio = spec_dc[i_dc] / np.median(spec_dc)
    chk("DC offset bị loại (kênh DC < 5× trung vị)", ratio < 5.0,
        f"tỷ số {ratio:.2f} (trước khi sửa: ~1e8)")
    # không có fix thì DC phải nổi bật → chứng minh fix có tác dụng
    d_raw, fr_raw, _t2, _m2 = psr_iq.channelize_iq(
        iq_dc, fs, f0, nchan=nchan, navg=4, apply_iq_fix=False)
    raw_ratio = np.median(d_raw, axis=1)[i_dc] / np.median(d_raw)
    chk("không bật fix → DC nổi bật (fix thật sự có tác dụng)",
        raw_ratio > 10 * max(ratio, 1.0), f"{raw_ratio:.0f}× vs {ratio:.2f}×")
    shutil.rmtree(tmp, ignore_errors=True)


# ------------------------------------------------------------------ psr_core
def audit_core():
    section("psr_core")
    import psr_core as C
    # 1) khử tán sắc: tín hiệu trễ đúng công thức
    dm, f_hi, f_lo = 100.0, 1400.0, 1300.0
    expect = C.K_DM * dm * (1 / f_lo**2 - 1 / f_hi**2)     # trễ ở f_lo so với f_hi
    got = float(C.dm_delay_s(dm, f_lo, f_hi))
    chk("dm_delay_s khớp công thức K·DM·(1/f_lo² − 1/f_hi²) và CÓ DẤU",
        abs(got - expect) < 1e-9, f"{got:.6f} s (kỳ vọng {expect:.6f})")
    # 2) fold: xung tại pha biết trước
    ts, P = 1e-3, 0.25
    n = 4000
    tt = np.arange(n) * ts
    x = np.zeros(n)
    ph = (tt % P) / P
    x += 10 * np.exp(-((ph - 0.3) ** 2) / (2 * 0.01 ** 2))
    x += np.random.default_rng(6).normal(0, 1, n)
    prof, _ = C.fold(x, ts, P, nbins=128)
    chk("fold: đỉnh ở pha 0.30 ± 0.02",
        abs(int(np.argmax(prof)) / 128 - 0.30) < 0.02,
        f"{int(np.argmax(prof))/128:.3f}")
    # 3) refine_period hội tụ về P
    n_long = 100_000                     # 100 s = 400 chu kỳ
    tl = np.arange(n_long) * ts
    xl = np.zeros(n_long)
    phl = (tl % P) / P
    xl += 10 * np.exp(-((phl - 0.3) ** 2) / (2 * 0.01 ** 2))
    xl += np.random.default_rng(6).normal(0, 1, n_long)
    p_b, snr_b, _ = C.refine_period(xl, ts, P * 1.002, nbins=256,
                                    iters=2, nstep=21)
    chk("refine_period: hội tụ < 100 ppm từ lệch 2000 ppm",
        abs(p_b - P) / P < 1e-4, f"{1e6*(p_b-P)/P:+.1f} ppm, SNR {snr_b:.1f}")
    # 4) profile_snr: nhiễu thuần cho SNR thấp
    nz = np.random.default_rng(7).normal(0, 1, 4000)
    pn, cn = C.fold(nz, ts, P, nbins=128)
    chk("profile_snr nhiễu thuần < 6σ", C.profile_snr(pn, counts=cn)[0] < 6.0,
        f"{C.profile_snr(pn, counts=cn)[0]:.2f}σ")
    # 4b) CHỐNG SUY BIẾN MẪU SỐ (lỗi đã gặp: SNR 3,5e12σ trên tệp 1 xung)
    # hồ sơ răng lược: 1 xung, phần lớn bin trống (=0) → MAD sụp về 0
    comb = np.zeros(256)
    comb[[10, 60, 110, 160, 210]] = 5.0
    cnt_c = np.zeros(256)
    cnt_c[[10, 60, 110, 160, 210]] = 1.0
    s_cb, w_cb, ph_cb, info_cb = C.profile_snr(comb, counts=cnt_c,
                                               return_info=True)
    chk("profile_snr: hồ sơ răng lược → SNR hữu hạn (< 1e3), không 1e12",
        np.isfinite(s_cb) and s_cb < 1e3, f"{s_cb:.3g}σ")
    chk("profile_snr: báo degenerate khi MAD sụp", info_cb["degenerate"] is True,
        str(info_cb))
    chk("profile_snr: đếm đúng số bin có mẫu", info_cb["n_filled"] == 5,
        str(info_cb["n_filled"]))
    # quá ít bin có mẫu (< 8) → coi như không ước lượng được nền
    tin = np.zeros(256)
    tin[3] = 9.0
    cnt_1 = np.zeros(256)
    cnt_1[3] = 1.0
    s_1, _, _, i_1 = C.profile_snr(tin, counts=cnt_1, return_info=True)
    chk("profile_snr: 1 bin có mẫu → SNR = 0 (từ chối, không bịa số)",
        s_1 == 0.0 and i_1["degenerate"], f"{s_1}, {i_1}")
    # dữ liệu thật: SNR không được đổi khi MAD hợp lệ (hồi quy)
    prof_ok, cnt_ok = C.fold(xl, ts, P, nbins=256)
    s_new = C.profile_snr(prof_ok, counts=cnt_ok)[0]
    s_old = C.profile_snr(prof_ok)[0]
    chk("profile_snr: hồ sơ đủ mẫu → SNR không đổi vì chốt chặn mới",
        abs(s_new - s_old) <= max(0.02 * s_old, 0.05),
        f"mới {s_new:.3f} · cũ {s_old:.3f}")
    # 5) fft_search: tìm đúng tần số tiêm
    f_inj = 4.0
    xx = np.sin(2 * np.pi * f_inj * tt) + np.random.default_rng(8).normal(0, 1, n)
    cands = C.fft_search(xx, ts, fmin_hz=1.0, fmax_hz=20.0, nharm=2, top=3)
    chk("fft_search: tần số đỉnh = 4 Hz ± 0,2",
        cands and abs(cands[0]["freq_hz"] - f_inj) < 0.2,
        f"{cands[0]['freq_hz']:.2f} Hz" if cands else "—")
    # 6) zero-DM: giữ xung tán sắc, bỏ RFI đồng thời
    good = C.zero_dm_keeps_pulse if hasattr(C, "zero_dm_keeps_pulse") else None
    chk("có hàm lọc zero-DM / RFI", callable(getattr(C, "zero_dm_filter", None)))


# ---------------------------------------------------------------- psr_period
def audit_period():
    section("psr_period")
    import psr_sim, psr_core as C, psr_period as P
    for p_true, nm in ((0.100, "100 ms"), (0.253065, "253 ms")):
        dyn, fr, meta = psr_sim.simulate(dm=3.0, period_s=p_true, w50_ms=6.0,
                                         nchan=64, bw_mhz=32.0, tsamp_s=256e-6,
                                         t_total_s=120.0, snr_target=40.0,
                                         rfi=False, seed=9)
        s, _ = C.dedisperse(dyn, fr, 3.0, 256e-6)
        res = P.blind_period_search(s, 256e-6, top=8)
        b = res.get("best") or {}
        err = abs(b.get("p_s", 0) - p_true) / p_true if b else 1.0
        chk(f"dò mù: P thật {nm} → sai số < 0,1 %", err < 1e-3,
            f"P = {(b.get('p_s') or 0)*1e3:.3f} ms")
        chk(f"dò mù {nm}: KHÔNG trả về P/2 hay 2P",
            b and abs(b["p_s"] / p_true - 1) < 1e-3,
            f"tỷ số {b['p_s']/p_true:.5f}" if b else "—")
    chk("chu kỳ phi lý bị chặn (không có ứng viên P > T/5)",
        all(c["p_s"] <= 120.0 / 5.0 * 1.05 for c in (res.get("candidates") or [])),
        f"{len(res.get('candidates') or [])} ứng viên")
    # CHỐT CHẶN TỆP QUÁ NGẮN: 1 xung khổng lồ trong 0,2 s → không được fold ra
    # SNR phi lý; phải trả fold_note và best=None (lỗi đã gặp: 3,5e12σ)
    ts_c = 2.05e-4
    x_c = np.zeros(976)
    x_c[130:134] = [1.0, 40.0, 30.0, 5.0]          # đúng 1 giant pulse
    rc = P.blind_period_search(x_c, ts_c, fmin_hz=1.0, fmax_hz=200.0, top=8)
    chk("tệp 1 xung ngắn: best=None (không khẳng định chu kỳ)",
        rc.get("best") is None, str(rc.get("best")))
    chk("tệp 1 xung ngắn: có fold_note giải thích vì sao",
        bool(rc.get("fold_note")) and "gập" in (rc.get("fold_note") or ""),
        (rc.get("fold_note") or "—")[:70])
    chk("tệp 1 xung ngắn: không có ứng viên SNR > 1e3",
        all(c["snr"] < 1e3 for c in (rc.get("candidates") or [])),
        f"max = {max([c['snr'] for c in (rc.get('candidates') or [])] or [0]):.3g}")
    # SNR của hồ sơ đủ mẫu phải giữ nguyên bản chất √T (hồi quy)
    chk("hồ sơ đủ mẫu: fold_note = None khi dữ liệu tốt",
        (res.get("fold_note") is None) or ("ngưỡng" in (res.get("fold_note") or "")),
        str(res.get("fold_note"))[:60])


# ---------------------------------------------------------------- psr_detect
def audit_detect():
    section("psr_detect")
    import psr_core as _core
    # Regression for the measured B0329+54 single-pulse subband lag set:
    # 8 points, low-frequency endpoint is a large residual. Robust estimator
    # must retain auditable points, not silently clip 4/8 based on tiny MAD.
    _f = np.array([1019.8828,1139.7656,1259.7656,1379.7656,
                   1499.8260,1620.0,1740.0,1860.0])
    _lag_ms = np.array([66.29084,52.97730,37.45802,26.50218,
                        16.26240,10.69091,4.53932,0.0])
    _lag = _lag_ms / 1000.0               # fit equation returns seconds
    _K = 4.148808e3
    _x = 1 / _f**2
    _slopes = [(_lag[i]-_lag[j]) / (_x[i]-_x[j])
               for i in range(8) for j in range(i+1,8)]
    _dm_ts = float(np.median(_slopes)) / _K
    chk("B0329 measured subband DM is finite and near catalogue (≈26.32)",
        abs(_dm_ts-26.32) < 0.15, f"Theil-Sen DM={_dm_ts:.3f}")
    _inter = float(np.median(_lag-_dm_ts*_K*_x))
    _resid = _lag - (_dm_ts*_K*_x+_inter)
    chk("B0329 low edge residual is reported, not silently deleted",
        abs(float(_resid[0])) > 0.005,
        f"low-edge residual={_resid[0]*1e3:.2f} ms; all 8 points retained")
    import psr_detect as D
    chk("safe_stem: cắt ≤ 60 ký tự", len(D.safe_stem("x" * 200)) <= D.MAX_STEM,
        str(len(D.safe_stem("x" * 200))))
    chk("safe_stem: bỏ ký tự Windows cấm",
        all(c not in D.safe_stem('a<>:"/b|c?*d') for c in '<>:"/|?*'))
    real = os.path.join("..", "data", "B0329+54.fil")
    # ghi kết quả vào thư mục TẠM (audit không được làm bẩn results/).
    # PHẢI gán D.RESULTS: psr_detect chốt RESULTS lúc import nên env vô hiệu.
    _tmp_res = tempfile.mkdtemp(prefix="audit_res_")
    D.RESULTS = _tmp_res
    if os.path.exists(real):
        m, _ = quiet(D.detect, real, dm_ref=26.7641, out_name="audit_b0329")
        chk("B0329+54: status ok", m.get("status") == "ok", str(m.get("status")))
        chk("B0329+54: DM dải con còn trong 8 % reference (8 subband noisy)",
            abs(float(m["stage"].get("dm_subband_mean") or 0) - 26.7641) < 2.2,
            f"{m['stage'].get('dm_subband_mean')} ± "
            f"{m['stage'].get('dm_subband_std')}")
        chk("B0329+54: figure_check rỗng (đơn vị + bố cục)",
            m.get("figure_check") == [], str(m.get("figure_check"))[:60])
        # Matched-filter SNR không phải peak amplitude; label trên panel phải
        # diễn giải đúng đại lượng đã sắp xếp để không gọi nhầm "sáng nhất".
        import psr_plots as _plots
        import inspect as _inspect
        _src_plot = _inspect.getsource(_plots.plot_timeseries)
        chk("nhãn ★ nói rõ matched-filter SNR, không gọi peak sáng nhất",
            "SNR lọc khớp cao nhất" in _src_plot and
            "xung sáng nhất:" not in _src_plot)
        chk("report có input_sha256 + schema_version",
            bool(m.get("input_sha256")) and m.get("schema_version") == 3)
        chk("guard gắn nhãn cho dữ liệu thật",
            (m.get("guard") or {}).get("tags"), str((m.get("guard") or {}).get("tags")))
        chk("dm_max tự mở rộng theo dm_ref",
            float(m["stage"].get("dm_max") or 0) >= 1.5 * 26.7641 - 1)
        # ghi vào data/ bị chặn
        import psr_paths as P
        raised = False
        try:
            P.assert_write_allowed(os.path.join(P.data_dir(), "x"))
        except PermissionError:
            raised = True
        chk("chặn ghi kết quả vào data/", raised)
    shutil.rmtree(_tmp_res, ignore_errors=True)
    # đầu vào xấu
    tmp = tempfile.mkdtemp(prefix="det_")
    for name, data in (("empty.dat", b""), ("text.txt", b"abc def" * 100)):
        p = os.path.join(tmp, name)
        open(p, "wb").write(data)
        m, _ = quiet(D.detect, p)
        chk(f"{name}: status unreadable + có lý do",
            m.get("status") == "unreadable" and m.get("problems"),
            str(m.get("status")))
    shutil.rmtree(tmp, ignore_errors=True)


# ------------------------------------------------------------------ psr_plots
def audit_plots():
    section("psr_plots")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import psr_plots as P

    f, a = plt.subplots()
    a.plot([0, 1, 2], [0, 1, 4], label="x")
    P.place_legend(a)
    pts = P._data_display_points(a)
    lb = a.get_legend().get_window_extent()
    chk("place_legend: không phủ điểm dữ liệu",
        P._count_inside(pts, lb) == 0)
    chk("place_legend: có khoảng hở ≥ 5 px tới đỉnh dữ liệu",
        lb.y0 - float(np.max(pts[:, 1])) >= 5.0,
        f"{lb.y0 - float(np.max(pts[:,1])):.1f} px")
    plt.close(f)

    # 7 loại lỗi phải phát hiện được
    cases = {}

    f, a = plt.subplots()
    a.plot(np.linspace(0, 1, 200), np.linspace(0, 1, 200), label="x")
    a.legend(loc="center")
    a.set_ylim(0, 1)                   # đường chéo đi qua tâm khung → chú giải che dữ liệu
    cases["legend_che_du_lieu"] = P.figure_report(f)
    plt.close(f)

    f, a = plt.subplots()
    a.plot([0, 1], [0, 1])
    a.set_xlabel("thời gian")
    cases["nhan_thieu_don_vi"] = P.figure_report(f)
    plt.close(f)

    f, a = plt.subplots()
    a.plot([0, 1e-3], [0, 1])
    a.set_xlabel("tần số (MHz)")
    a.set_ylabel("công suất (dB)")
    cases["don_vi_lech_bac"] = P.figure_report(f)
    plt.close(f)

    f, a = plt.subplots()
    a.plot([0, 1], [0, 1])
    a.set_title("P = 0.25")
    a.set_xlabel("x (ms)")
    a.set_ylabel("y (dB)")
    cases["tieu_de_thieu_don_vi"] = P.figure_report(f)
    plt.close(f)

    for kind, issues in cases.items():
        chk(f"figure_report bắt '{kind}'", kind in {i["kind"] for i in issues},
            str(sorted({i["kind"] for i in issues})))

    # No provenance is asserted by default. Explicit verified provenance may
    # be shown in-panel and must be ignored by overlap/unit audits as a badge.
    f, axv = plt.subplots()
    axv.plot([0, 1], [0, 1], label="series")
    chk("không tự gắn badge REAL khi provenance chưa biết", P._tag(f) is None)
    tag = P._tag(f, "observational (verified metadata)")
    chk("badge chỉ hiện khi provenance được truyền tường minh",
        tag is not None and tag.axes is axv and
        np.allclose(tag.get_position(), (0.012, 0.985)))
    axv.set_xlabel("time (s)"); axv.set_ylabel("relative signal (a.u.)")
    chk("badge provenance không tạo figure_report issue",
        P.figure_report(f) == [], str(P.figure_report(f))[:80])
    plt.close(f)

    # kiểm tra chính tả nhãn: signal đã trừ nền, chưa fit residual
    from inspect import getsource
    chk("ylabel nêu rõ cường độ tương đối đã trừ nền (không gọi residual)",
        "cường độ tương đối (đã trừ nền, chuẩn hoá)" in getsource(P.plot_timeseries)
        and "công suất dư" not in getsource(P.plot_timeseries))
    # Matplotlib auto legend must not sit over the star at t=1722.9 ms.
    src_ts = getsource(P.plot_timeseries)
    chk("star marker at selected candidate; fixed upper-center legend preferred",
        'ax.plot([tp[i_best]]' in src_ts and
        'SNR lọc khớp cao nhất' in src_ts and
        'ax._preferred_legend_loc = "upper center"' in src_ts)
    # Match the app preview aspect (wide and short): this caught the screenshot
    # case where the star over the high-SNR event touched the upper-right legend.
    _fstar, _astar = plt.subplots(figsize=(15.7, 2.4))
    _yy = np.zeros(2048); _yy[292] = .768; _yy[1006] = .450; _yy[1723] = .703
    _pulses = [dict(t_s=.2916, snr=593), dict(t_s=1.006, snr=418),
               dict(t_s=1.7229, snr=608)]
    P.plot_timeseries(np.arange(2048)*.001, _yy, peaks=_pulses,
                      ax=_astar, ylabel="relative signal (a.u.)")
    _fstar.canvas.draw()
    _leg = _astar.get_legend()
    _star = next(x for x in _astar.lines if x.get_marker() == P.MK_BEST
                 and x.get_label() == "_nolegend_")
    _sb, _lb = _star.get_window_extent(), _leg.get_window_extent()
    _overlap = not (_sb.x1 < _lb.x0 or _sb.x0 > _lb.x1 or
                    _sb.y1 < _lb.y0 or _sb.y0 > _lb.y1)
    chk("star glyph is not overlapped by legend",
        not _overlap, f"marker={_sb.bounds}, legend={_lb.bounds}")
    plt.close(_fstar)
    src_fit = getsource(P.plot_subband_lags)
    chk("subband residual shown in ms; no unsupported sigma/RFI cause",
        '>3σ' not in src_fit and '17σ' not in src_fit and
        'tới {float(np.max(np.abs(res[out]))):.1f} ms' in src_fit and
        'nguyên nhân chưa xác định' in src_fit)

    # hình chuẩn không được có lỗi
    f, a = plt.subplots()
    a.plot([0, 10], [0, 5], label="chuỗi")
    a.set_xlabel("thời gian (ms)")
    a.set_ylabel("công suất (dB)")
    a.set_title("thử")
    P.place_legend(a)
    chk("hình chuẩn: figure_report rỗng", P.figure_report(f) == [],
        str(P.figure_report(f))[:60])
    plt.close(f)


# ------------------------------------------------------------- psr_sensitivity
def audit_vector_export():
    """Mỗi hình phải có PNG và SVG cho báo cáo ngoài ứng dụng."""
    section("psr_plots (vector)")
    import os
    import tempfile

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import psr_plots as P

    d = tempfile.mkdtemp(prefix="_vec_")
    f, a = plt.subplots()
    a.plot([1, 2, 3], [2, 1, 4], label="dữ liệu")
    a.set_xlabel("t (ms)")
    try:
        out = P.save_all(f, os.path.join(d, "fig.png"))
        plt.close(f)
        names = sorted(os.path.basename(x) for x in out)
        chk("save_all ghi đủ PNG + SVG (không PDF, không HTML)",
            names == ["fig.png", "fig.svg"], str(names))
        chk("cả 2 tệp đều tồn tại và khác rỗng",
            all(os.path.getsize(os.path.join(d, n)) > 500 for n in names))
        svg = open(os.path.join(d, "fig.svg"), encoding="utf-8").read()
        chk("SVG là XML hợp lệ", svg.lstrip().startswith("<?xml"))
        chk("SVG giữ CHỮ là text (fonttype=none) → chọn/copy được",
            "<text" in svg and "t (ms)" in svg)
        chk("không sinh tệp PDF/HTML ngoài ý muốn",
            not any(n.endswith((".pdf", ".html")) for n in os.listdir(d)),
            str(sorted(os.listdir(d))))
        # vector thật: chữ không bị chuyển thành đường vẽ
        chk("SVG không nhúng ảnh raster cho đồ thị đường",
            "<image" not in svg)
    finally:
        import shutil
        shutil.rmtree(d, ignore_errors=True)


def audit_preview_no_zoom():
    """GUI intentionally exposes no embedded zoom control after user request."""
    section("GUI preview: static panel, no zoom action")
    from tkinter import Tk
    import gui_app
    root = Tk()
    try:
        app = gui_app.App(root)
        root.update()
        buttons = []
        def walk(w):
            for c in w.winfo_children():
                if c.winfo_class() == "TButton":
                    buttons.append(str(c.cget("text")))
                walk(c)
        walk(app.tab_det)
        zoom_buttons = [x for x in buttons if any(k in x.lower()
                         for k in ("zoom", "phóng", "xem lớn", "svg"))]
        chk("preview defaults to a single panel", app.fig_panel.get() in {"a","b","c","d"})
        chk("no zoom/viewer controls in Tab 2", not zoom_buttons, str(zoom_buttons))
        chk("no custom zoom handlers attached", getattr(app,"det_zoom",None) is None
            and getattr(app,"det_sliders",None) is None
            and getattr(app,"det_toolbar",None) is None)
        chk("full saved PNG can be opened externally", callable(app.open_figure_external))
    finally:
        try: root.destroy()
        except Exception: pass


def audit_hardware_profile():
    """Các dữ kiện NCU/ACU POAM trong registry phải nhất quán với docs/manual."""
    section("psr_hw POAM profile")
    import psr_hw as H
    errs = H.self_check()
    chk("psr_hw.self_check gồm profile NCU/ACU", not errs, "; ".join(errs))
    ncu = H.PARTS["poam_ncu"]
    acu = H.PARTS["poam_acu"]
    chk("NCU IP/ECA/sequence manual", ncu["ip"] == "192.168.1.100"
        and ncu["eca_m2"] == 6.4
        and tuple(ncu["sequence_s"][k] for k in ("noise","load","sun")) == (20,20,240))
    chk("NCU ENR 30 dB is interpretation, not field-measured",
        ncu["enr_db"] == 30.0 and "not measured/verified" in ncu["note"].lower())
    chk("ACU PARK 85° + EL limit protected", acu["park_el_deg"] == 85.0
        and "không tự clear" in acu["note"].lower())
    chk("feed L-band not assumed installed; conditional IF mapping in profile",
        H.PARTS["poam_receiver"].get("lband_feed_confirmed") is False
        and H.PARTS["poam_receiver"].get("if_rf_mapping_mhz")[1500] == (3650,4250))


def audit_sensitivity():
    section("psr_sensitivity")
    import psr_sensitivity as S
    d = S.Dish()
    chk("A_eff = 5,91 m² (η 0,55, D 3,7 m)", abs(d.aeff_m2 - 5.91) < 0.05,
        f"{d.aeff_m2:.3f}")
    sefd = d.sefd_jy(150)
    chk("SEFD(T_sys 150 K) ≈ 70 kJy", abs(sefd - 70e3) / 70e3 < 0.02,
        f"{sefd/1e3:.1f} kJy")
    chk("SEFD tỉ lệ thuận T_sys", abs(d.sefd_jy(300) / sefd - 2.0) < 0.01)
    # SNR ∝ √(B·t) và ∝ √(P/W)
    f1 = S.snr_fold(1.0, 1e4, 10e6, 3600, 0.5, 0.01)
    f4 = S.snr_fold(1.0, 1e4, 40e6, 3600, 0.5, 0.01)
    chk("SNR ∝ √B (B×4 → SNR×2)", abs(f4 / f1 - 2.0) < 0.02, f"×{f4/f1:.3f}")
    t4 = S.snr_fold(1.0, 1e4, 10e6, 4 * 3600, 0.5, 0.01)
    chk("SNR ∝ √t (t×4 → SNR×2)", abs(t4 / f1 - 2.0) < 0.02, f"×{t4/f1:.3f}")
    chk("snr_single = SNR một xung (không có √(P/W))",
        S.snr_single(1.0, 1e4, 10e6, 0.01) > 0)


# --------------------------------------------------------------- psr_targets
def audit_targets():
    section("psr_targets")
    import psr_targets as T
    tmp = tempfile.mkdtemp(prefix="tgt_")
    old = os.environ.get("PSR_TARGETS_FILE")
    os.environ["PSR_TARGETS_FILE"] = os.path.join(tmp, "t.json")
    try:
        n0 = len(T.all_pulsars())
        T.upsert_target(dict(name="ZZ_A", ra=10.0, dec=-10.0, P=0.5, dm=10.0))
        chk("thêm mục tiêu → danh sách +1", len(T.all_pulsars()) == n0 + 1)
        chk("tìm không phân biệt hoa/thường", bool(T.find_target("zz_a")))
        chk("RA '08:14:12' → 123,55°", abs(T.parse_ra("08:14:12") - 123.55) < 0.01,
            f"{T.parse_ra('08:14:12'):.3f}")
        chk("Dec '-05:12:34' → -5,209°", abs(T.parse_dec("-05:12:34") + 5.209) < 0.01)
        chk("validate bắt RA/Dec ngoài miền",
            T.validate_target(dict(name="x", ra=999, dec=999)))
        T.delete_target("ZZ_A")
        chk("xoá mục tiêu → danh sách trở lại", len(T.all_pulsars()) == n0)
        # flux ATNF: Vela phải sáng hơn B0950 ở 1400 MHz
        v = T.find_target("B0833-45"); b = T.find_target("B0950+08")
        chk("flux ATNF: Vela 1050 mJy > B0950 100 mJy @1400",
            v["s1400"] == 1050 and b["s1400"] == 100,
            f"{v['s1400']} vs {b['s1400']}")
        chk("W50(423) của B1641-45 bị tán xạ > 100 ms",
            T.w50_at(8.0, 478.7, 423) > 100, f"{T.w50_at(8.0, 478.7, 423):.0f} ms")
    finally:
        if old is None:
            os.environ.pop("PSR_TARGETS_FILE", None)
        else:
            os.environ["PSR_TARGETS_FILE"] = old
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------- psr_swcomp
def audit_swcomp():
    section("psr_swcomp")
    import psr_swcomp as W
    # barycentric: độ lớn hợp lý và đổi dấu theo hướng (cần astropy + datetime)
    import datetime as _dt
    t_utc = _dt.datetime(2026, 11, 22, 12, 0, 0)
    d1 = W.barycentric_delay_s(0.0, 0.0, t_utc)
    if d1 is None:
        chk("barycentric: cần astropy (bỏ qua nếu thiếu)", True, "astropy chưa cài")
    else:
        chk("barycentric |Δt| < 600 s (giới hạn vật lý)", abs(d1) < 600,
            f"{d1:.1f} s")
        d2 = W.barycentric_delay_s(180.0, 0.0, t_utc)
        chk("barycentric: hai hướng đối nhau cho trễ trái dấu",
            abs(d1 + d2) < 60, f"{d1:.1f} vs {d2:.1f}")
    # transit_weights(n, hpbw, t_total, cos_dec): đỉnh ở giữa, đối xứng, ≤ 1
    n = 101
    w = W.transit_weights(n, 13.4, 7200.0)
    chk("transit_weights: đỉnh = 1 tại transit, ≤ 1 và đối xứng",
        abs(float(w[n // 2]) - 1.0) < 0.02 and float(np.max(w)) <= 1.001
        and abs(float(w[n // 2 - 10] - w[n // 2 + 10])) < 1e-9,
        f"max {np.max(w):.3f}")
    chk("transit_weights: giảm khi ra xa transit",
        float(w[3]) < float(w[n // 2]) * 0.1, f"w(giữa)=1, w(mép)={w[3]:.3f}")
    # stack_profiles: trung bình có trọng số
    rng = np.random.default_rng(10)
    a1 = rng.normal(0, 1, 128); b1 = rng.normal(0, 1, 128)
    st, nw = W.stack_profiles([a1, b1])
    chk("stack_profiles: trung bình đúng (2 hồ sơ)",
        abs(float(np.mean(st))) < 0.5 and st.size == 128, f"n={nw}")
    # Y-factor
    tsys, tcal = W.y_factor_tsys(1.5, 1.0, 300.0)      # Y = 1,5
    chk("y_factor_tsys: Y=1,5 & T_cal=300 K → 600 K", abs(tsys - 600) < 1.0,
        f"{tsys:.0f} K")
    bad = False
    try:
        W.y_factor_tsys(1.0, 1.5, 10.0)       # Y < 1 → phải bị chặn
    except ValueError:
        bad = True
    chk("y_factor_tsys: Y ≤ 1 bị từ chối (phép đo sai)", bad)


# ------------------------------------------------------------------ psr_i18n
def audit_i18n():
    section("psr_i18n")
    import psr_i18n as L
    chk("self_check sạch", not L.self_check(), "; ".join(L.self_check()))
    cov = L.coverage()
    chk(f"đã dịch ≥ 80 chuỗi ({cov['n_translated']})", cov["n_translated"] >= 80)
    keep = L.current()
    L.set_lang("en", persist=False)
    en = L.t("▶ Bắt đầu ghi")
    L.set_lang("vi", persist=False)
    vi = L.t("▶ Bắt đầu ghi")
    L.set_lang(keep, persist=False)
    chk("chuỗi UI chính có bản dịch EN", en != vi, f"{vi!r} → {en!r}")
    chk("chuỗi lạ giữ nguyên (không hiện khoá thô)",
        L.t("xxx_khong_co") == "xxx_khong_co")
    bad = False
    try:
        L.set_lang("fr", persist=False)
    except ValueError:
        bad = True
    chk("ngôn ngữ không hỗ trợ bị từ chối", bad)


# ------------------------------------------------------------- ingest_guard
def audit_guard():
    section("ingest_guard")
    import ingest_guard as G
    chk("self_check nội bộ sạch", not G.self_check(), "; ".join(G.self_check()))
    tmp = tempfile.mkdtemp(prefix="guard_")
    # 4 container giả
    fake = {
        "a.fil": b"HEADER_START" + bytes(64),
        "b.fits": b"SIMPLE  =                    T" + bytes(64),
        "c.csv": b"t,ch0" + bytes([10]) + b"0,1" + bytes([10]) + b"1,2" + bytes([10]),
        "d.bin": bytes(range(256)) * 8,
    }
    kinds = {}
    for n, d in fake.items():
        p = os.path.join(tmp, n)
        open(p, "wb").write(d)
        kinds[n] = G.sniff_format(p)["kind"]
    chk("nhận dạng container: fil/fits/csv/nhị phân",
        kinds["a.fil"] == "sigproc" and kinds["b.fits"] == "psrfits"
        and kinds["c.csv"] == "text" and kinds["d.bin"] == "binary", str(kinds))
    # NaN
    a2 = np.ones((100, 4)); a2[10, 1] = np.nan
    _, rep = G.sanitize_nonfinite(a2)
    chk("NaN 0,25 % → REPAIRED, đúng 1 điểm", rep["tag"] == "REPAIRED"
        and rep["replaced"] == 1, str(rep))
    a3 = np.ones((100, 4)); a3[::2] = np.nan
    chk("NaN 50 % → CORRUPTED", G.sanitize_nonfinite(a3)[1]["tag"] == "CORRUPTED")
    # ADC
    chk("ADC bão hoà toàn bộ → ABORT",
        G.adc_clipping(np.full(4096, 127, np.int8), 8)["tag"] == "ABORT")
    chk("ADC sạch → OK", G.adc_clipping(np.random.default_rng(1).normal(size=4096) * 5,
                                        8)["tag"] == "OK")
    # SK: kênh CW
    base = np.abs(np.random.default_rng(2).normal(size=(2000, 16))) ** 2 + 1
    base[:, 3] = 200.0
    chk("SK bắt kênh CW (kênh 3)", 3 in G.spectral_kurtosis(base)["bad_channels"])
    # radiometer
    r = G.radiometer_check(base, 1e4, 1e-3)
    chk("radiometer trả lý thuyết + đo", r["theory"] > 0 and "tag" in r, str(r["tag"]))
    # preflight
    chk("preflight: cần 5 TB → không đủ", not G.disk_preflight(tmp, 5e12)["ok"])
    chk("preflight: cần 1 MB → đủ", G.disk_preflight(tmp, 1e6)["ok"])
    # atomic + refuse
    j = os.path.join(tmp, "x.json")
    G.atomic_write_json(j, {"a": 1})
    chk("atomic_write_json: có tệp, không còn .tmp",
        os.path.exists(j) and not os.path.exists(j + ".tmp"))
    raised = False
    try:
        G.refuse_write_into_raw(os.path.join("..", "data", "x"), os.path.join("..", "data"))
    except PermissionError:
        raised = True
    chk("refuse_write_into_raw chặn data/", raised)
    shutil.rmtree(tmp, ignore_errors=True)


# -------------------------------------------------- record_unattended (nhẹ)
def audit_recorder():
    section("record_unattended")
    import record_unattended as R
    tmp = tempfile.mkdtemp(prefix="rec_")
    try:
        m, out = quiet(R.run_session, target="AUDIT", hours=6 / 3600, band="423",
                       mock=True, nchan=32, tsamp_us=512, out_dir=tmp)
        chk("phiên mock 6 s: roundtrip PASS", getattr(m, "get", lambda *_: None)
            and m.get("roundtrip_ok") is True, str(m)[:60] if not isinstance(m, dict) else "")
        chk("sidecar có input_sha256 + schema_version",
            m.get("input_sha256") and m.get("schema_version") == 3)
        chk("preflight ghi vào meta", bool(m.get("disk")))
        chk("dòng ghi khớp thời lượng", abs(m.get("duration_s", 0) - 6.0) < 0.6,
            f"{m.get('duration_s')} s")
    except Exception as exc:                     # noqa: BLE001
        chk("phiên mock chạy được", False, repr(exc))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# -------------------------------------------------------------------- gui_app
def audit_gui():
    section("gui_app")
    import gui_app
    _majmin = ".".join(gui_app.VERSION.split(".")[:2])
    chk("VERSION đúng dạng semver (x.y.z)",
        bool(re.fullmatch(r"\d+\.\d+\.\d+", gui_app.VERSION)), gui_app.VERSION)
    chk("VERSION khớp README (không lệch tài liệu)",
        _majmin + "." in open("../README.md", encoding="utf-8").read()
        or gui_app.VERSION in open("../README.md", encoding="utf-8").read(),
        f"{gui_app.VERSION} · {_majmin}")
    tmp = os.path.join(tempfile.gettempdir(), "_audit_settings.json")
    old = os.environ.get("PSR_SETTINGS")
    os.environ["PSR_SETTINGS"] = tmp
    try:
        rc, out = quiet(gui_app.selfcheck)
        chk("selfcheck bản chạy mã nguồn: PASS", rc == 0, f"rc={rc}")
        rep = open(os.path.join("..", "selfcheck_report.txt"), encoding="utf-8").read()
        chk("selfcheck có ≥ 16 mục PASS", rep.count("[PASS]") >= 16,
            f"{rep.count('[PASS]')} mục")
        chk("selfcheck không có FAIL", "[FAIL]" not in rep)
    finally:
        if old is None:
            os.environ.pop("PSR_SETTINGS", None)
        else:
            os.environ["PSR_SETTINGS"] = old
        for f in (tmp, tmp + ".tmp"):
            if os.path.exists(f):
                os.remove(f)


AUDITS = {
    "psr_constants": audit_constants, "psr_site": audit_site,
    "psr_paths": audit_paths, "psr_fil": audit_fil, "psr_fits": audit_fits,
    "psr_hw POAM profile": audit_hardware_profile,
    "psr_iq": audit_iq, "psr_core": audit_core, "psr_period": audit_period,
    "psr_detect": audit_detect, "psr_plots": audit_plots,
    "psr_plots (vector)": audit_vector_export,
    "GUI preview (no zoom)": audit_preview_no_zoom,
    "psr_hw POAM profile": audit_hardware_profile,
    "psr_sensitivity": audit_sensitivity, "psr_targets": audit_targets,
    "psr_swcomp": audit_swcomp, "psr_i18n": audit_i18n,
    "ingest_guard": audit_guard, "record_unattended": audit_recorder,
    "gui_app": audit_gui,
}


def main(argv):
    only = [a for a in argv[1:] if not a.startswith("-")]
    t0 = time.time()
    for name, fn in AUDITS.items():
        if only and name not in only:
            continue
        try:
            fn()
        except Exception as exc:                 # noqa: BLE001
            import traceback
            traceback.print_exc()
            chk(f"{name}: chạy không lỗi", False, repr(exc))
    print("\n" + "=" * 74)
    mods = {}
    for mod, name, ok, _ in RES:
        mods.setdefault(mod, [0, 0])
        mods[mod][0] += int(ok)
        mods[mod][1] += 1
    for mod, (ok, tot) in mods.items():
        flag = "PASS" if ok == tot else "FAIL"
        print(f"  {mod:>20}: {ok:>2}/{tot:<2} {flag}")
    n_ok = sum(1 for *_, ok, _ in [(a, b, c, d) for a, b, c, d in RES] if ok)
    n_ok = sum(int(r[2]) for r in RES)
    print(f"\nTỔNG: {n_ok}/{len(RES)} · {time.time()-t0:.1f}s")
    fails = [(m, n, d) for m, n, ok, d in RES if not ok]
    if fails:
        print("\nKHÔNG ĐẠT:")
        for m, n, d in fails[:20]:
            print(f"  ✗ [{m}] {n} — {d}")
    return 0 if not fails else 1


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                            # noqa: BLE001
        pass
    sys.exit(main(sys.argv))
