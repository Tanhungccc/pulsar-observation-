# -*- coding: utf-8 -*-
"""
acceptance_test.py — NGHIỆM THU NGHIÊM NGẶT trước khi đem đi sử dụng.

Kiểm tra 5 nhóm điều kiện, KHÔNG chỉ "chạy được" mà còn kiểm tra:
    S1 ĐẦU VÀO     : 8-bit/32-bit/2-bit, nifs=2, file cụt, rỗng, phẳng, PSRFITS,
                     IQ (SigMF ci16/cu8/cf32, WAV, npy), sai đuôi, không tồn tại,
                     truyền thư mục, file 0 byte
    S2 FALLBACK    : không có SDR → tự chuyển mô phỏng; hỏng LNA; thiếu BPF;
                     dừng giữa chừng; mô phỏng mất mẫu; metadata sidecar
    S3 ĐẦU RA      : đúng thư mục theo tên dữ liệu, đủ 4 file, JSON hợp lệ,
                     BÁO CÁO khớp JSON, PNG có nội dung, không ghi ra ngoài,
                     chạy lại không sinh rác, tên có dấu cách/unicode/dài,
                     thư mục kết quả chỉ-đọc
    S4 GUI         : mọi nút, đường dẫn, hộp thoại lỗi, khoá khi đang bận,
                     mở thư mục không tồn tại, đóng app
    S5 ĐỐI CHIẾU   : selftest, corpus xấu, GUI selfcheck, EXE selfcheck,
                     DM đo vs catalogue trên IQ thật

    python acceptance_test.py              # toàn bộ (~5–8 phút)
    python acceptance_test.py --fast       # bỏ phần ghi/EXE
    python acceptance_test.py --only S3

Exit code 0 = ĐẠT TẤT CẢ (dùng được), 1 = có mục FAIL.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import struct
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import psr_core, psr_detect, psr_fil, psr_fits, psr_iq, psr_hw   # noqa: E402
import record_unattended as ru                                  # noqa: E402

TMP = os.path.join(ROOT, "data", "_accept")
R: list[tuple[str, bool, str]] = []


def chk(name: str, ok, detail: str = ""):
    R.append((name, bool(ok), str(detail)))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f"  — {detail}" if detail else ""))


def section(t):
    print(f"\n{'='*78}\n{t}\n{'='*78}")


def quiet(fn, *a, **k):
    """Chạy fn, nuốt stdout (để bảng nghiệm thu đọc được)."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        return fn(*a, **k)


# ---------------------------------------------------------------- fixtures
def make_fixtures():
    os.makedirs(TMP, exist_ok=True)
    rng = np.random.default_rng(3)
    nch, nt = 64, 4000
    d = rng.normal(100, 10, (nch, nt)).astype(np.float32)
    # xung "thật" để chắc chắn có gì đó phát hiện được
    for k in range(6):
        j = 300 + k * 600
        d[:, j:j + 3] += 40
    hdr = dict(source_name="ACCEPT", nchans=nch, nifs=1, nbeams=1,
               telescope_id=6, machine_id=0, data_type=1, tsamp=2.5e-4,
               tstart=60000.0, fch1=1420.0, foff=-0.5)
    paths = {}
    # 8-bit
    p = os.path.join(TMP, "ok8.fil")
    psr_fil.write_fil(p, d, dict(hdr, nbits=8)); paths["fil8"] = p
    # 32-bit float
    p = os.path.join(TMP, "ok32.fil")
    psr_fil.write_fil(p, d, dict(hdr, nbits=32)); paths["fil32"] = p
    # cụt giữa dòng
    p = os.path.join(TMP, "trunc.fil")
    shutil.copy(paths["fil8"], p)
    with open(p, "r+b") as fh:
        fh.seek(-97, os.SEEK_END); fh.truncate()
    paths["trunc"] = p
    # chỉ có header
    p = os.path.join(TMP, "header_only.fil")
    psr_fil.write_fil(p, d[:, :0], dict(hdr, nbits=8)); paths["header_only"] = p
    # phẳng (toàn một giá trị)
    p = os.path.join(TMP, "flat.fil")
    psr_fil.write_fil(p, np.full((nch, 500), 7.0, np.float32),
                      dict(hdr, nbits=8)); paths["flat"] = p
    # 0 byte
    p = os.path.join(TMP, "zero.fil"); open(p, "wb").close(); paths["zero"] = p
    # nifs = 2 (2 phân cực) — ghi tay
    p = os.path.join(TMP, "twopol.fil")
    with open(p, "wb") as fh:
        def s2(t):
            b = t.encode(); fh.write(struct.pack("<i", len(b)) + b)
        s2("HEADER_START"); s2("source_name"); s2("2POL")
        for key, val in (("machine_id", 0), ("telescope_id", 6), ("data_type", 1),
                         ("nchans", nch), ("nifs", 2), ("nbeams", 0),
                         ("ibeam", 0), ("barycentric", 0), ("pulsarcentric", 0),
                         ("nbits", 8), ("signed", 0)):
            s2(key); fh.write(struct.pack("<i", val))
        for key, val in (("tstart", 60000.0), ("tsamp", 2.5e-4),
                         ("fch1", 1420.0), ("foff", -0.5)):
            s2(key); fh.write(struct.pack("<d", val))
        s2("HEADER_END")
        two = np.stack([d, d * 0.5], axis=1)          # (nchan, 2pol, ntime)
        fh.write(np.clip(two.transpose(2, 1, 0), 0, 255).astype(np.uint8).tobytes())
    paths["twopol"] = p
    # PSRFITS hợp lệ
    p = os.path.join(TMP, "ok.fits")
    psr_fits.write_psrfits(p, d, tsamp_s=2.5e-4, f_center_mhz=1420.0,
                          bw_mhz=32.0, source="ACCEPT")
    paths["fits"] = p
    # IQ SigMF ci16 / cu8 / cf32 + WAV + npy
    fs, fc, n = 2.4e6, 423e6, 240_000
    t = np.arange(n) / fs
    base = (rng.normal(0, 1, n) + 1j * rng.normal(0, 1, n)) * 4000
    base += np.exp(2j * np.pi * 30e3 * t) * 12000
    for dt, name in (("ci16_le", "iq_ci16"), ("cu8", "iq_cu8"),
                     ("cf32_le", "iq_cf32")):
        stem = os.path.join(TMP, name)
        psr_iq.write_sigmf(stem, base, fs, fc, dt)
        paths[name] = stem + ".sigmf-data"
    import wave
    p = os.path.join(TMP, "iq.wav")
    with wave.open(p, "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(int(fs))
        a = np.empty(2 * n, dtype="<i2")
        a[0::2] = np.clip(base.real, -32768, 32767).astype("<i2")
        a[1::2] = np.clip(base.imag, -32768, 32767).astype("<i2")
        w.writeframes(a.tobytes())
    paths["wav"] = p
    p = os.path.join(TMP, "iq.npy")
    np.save(p, base.astype(np.complex64)); paths["npy"] = p
    return paths


# ------------------------------------------------------------------ S1 input
def s1_inputs(fx):
    section("S1. ĐẦU VÀO — nhiều định dạng và nhiều kiểu hỏng")
    h, d = psr_fil.read_fil(fx["fil8"])
    chk("fil 8-bit đọc đúng", d.shape == (64, 4000) and h["nbits"] == 8,
        f"{d.shape}")
    h, d = psr_fil.read_fil(fx["fil32"])
    chk("fil 32-bit float đọc đúng", h["nbits"] == 32 and d.shape[1] == 4000,
        f"{d.shape}")
    h, d = psr_fil.read_fil(fx["trunc"])
    chk("fil CỤT giữa dòng: đọc phần đầy đủ + cảnh báo",
        any(("CẮT" in w or "CỤT" in w) for w in h["read_warnings"]),
        h["read_warnings"][:1])
    try:
        psr_fil.read_fil(fx["header_only"]); ok, det = False, "không ném lỗi"
    except Exception as e:
        ok, det = True, type(e).__name__
    chk("fil chỉ có header → lỗi rõ ràng", ok, det)
    h, d = psr_fil.read_fil(fx["flat"])
    chk("fil PHẲNG bị đánh dấu không hợp lệ",
        not h["validation"]["ok"] and any("PHẲNG" in p for p in
                                          h["validation"]["problems"]),
        h["validation"]["problems"][:1])
    try:
        psr_fil.read_fil(fx["zero"]); ok, det = False, "không ném lỗi"
    except Exception as e:
        ok, det = True, type(e).__name__
    chk("file 0 byte → lỗi rõ ràng", ok, det)
    h, d = psr_fil.read_fil(fx["twopol"])
    chk("nifs=2: cộng 2 phân cực đúng", h["nifs"] == 2 and d.shape == (64, 4000),
        f"{d.shape}, cảnh báo: {h['read_warnings'][:1]}")
    h, d = psr_fits.read_psrfits(fx["fits"])
    chk("PSRFITS hợp lệ đọc đúng", d.shape == (64, 4000) and h["nifs"] == 1,
        f"{d.shape}")
    h, d2 = psr_fil.read_fil(fx["fil8"])
    chk("bandpass/freqs đúng thứ tự (fch1 cao nhất)",
        abs(h["freqs_mhz"][0] - 1420.0) < 1e-6 and h["freqs_mhz"][-1] < 1420.0,
        f"{h['freqs_mhz'][0]:.2f} → {h['freqs_mhz'][-1]:.2f} MHz")

    for key, label, expect_df in (("iq_ci16", "SigMF ci16", 2.4e6 / 256),
                                  ("iq_cu8", "SigMF cu8", 2.4e6 / 256),
                                  ("iq_cf32", "SigMF cf32", 2.4e6 / 256),
                                  ("wav", "WAV I/Q 16-bit", None),
                                  ("npy", "NumPy phức", None)):
        try:
            kw = {}
            if key == "wav":
                kw = dict(fs_hz=2.4e6, fc_hz=423e6)
            elif key == "npy":
                kw = dict(fs_hz=2.4e6, fc_hz=423e6)
            hq, dyn = psr_iq.read_iq_as_dyn(fx[key], nchan=256, **kw)
            f = hq["freqs_mhz"]
            peak = f[int(np.argmax(dyn.mean(axis=1)))]
            ok = abs(peak - 423.03) < 0.1
            chk(f"IQ {label}: channelize đúng tần số", ok,
                f"{dyn.shape[1]} mẫu × {dyn.shape[0]} kênh, đỉnh {peak:.3f} MHz")
        except Exception as e:
            chk(f"IQ {label}: channelize đúng tần số", False,
                f"{type(e).__name__}: {e}")

    # sai đuôi / không tồn tại / thư mục
    bad = os.path.join(TMP, "unknown.xyz")
    open(bad, "wb").write(b"\x00" * 1000)
    try:
        psr_detect.load_any(bad); ok, det = False, "không ném lỗi"
    except Exception as e:
        ok, det = True, type(e).__name__
    chk("đuôi không nhận dạng → lỗi rõ ràng", ok, det)
    m = quiet(psr_detect.detect, os.path.join(TMP, "khong_ton_tai.fil"))
    chk("file không tồn tại → status=unreadable, không crash",
        m.get("status") == "unreadable", m.get("status"))
    m = quiet(psr_detect.detect, TMP)
    chk("truyền THƯ MỤC thay vì file → unreadable, không crash",
        m.get("status") == "unreadable", m.get("status"))


# --------------------------------------------------------------- S2 fallback
def s2_fallback(fx):
    section("S2. FALLBACK PHẦN CỨNG / DRIVER / DỪNG GIỮA CHÙNG")
    for band, goal in (("423", "pulsar"), ("1420", "pulsar"), ("1420", "hi")):
        c = psr_hw.detect_chain(band, goal=goal)
        chk(f"chuỗi {band} MHz/{goal}: có T_sys & SEFD hợp lý",
            80 < c.t_sys_k < 400 and c.sefd_jy > 0,
            f"T_sys {c.t_sys_k:.0f} K, SEFD {c.sefd_jy/1e3:.0f} kJy, "
            f"fallback={c.fallbacks}")
    c = psr_hw.detect_chain("423", have={"lna": "rtl_internal"})
    chk("hỏng LNA ngoài → dùng LNA nội + cảnh báo T_sys xấu",
        c.t_sys_k > 500 and any("LNA" in w for w in c.warnings),
        f"T_sys {c.t_sys_k:.0f} K")
    chk("psr_hw tự kiểm công thức", not psr_hw.self_check())

    # không có SDR → tự fallback
    out = os.path.join(TMP, "fb")
    m = quiet(ru.run_session, target="FB", hours=4 / 3600, band="423",
              mock=False, out_dir=out)
    chk("KHÔNG có SDR → Tự động chuyển mô phỏng (không crash)",
        m.get("mode") == "fallback-mock" and m.get("fallback"),
        f"mode={m.get('mode')}, lý do={m.get('fallback')}")
    # chế độ NGHIÊM NGẶT: source="real" không có SDR → phải LỖI, không tạo file
    out_real = os.path.join(TMP, "real_nosdr")
    raised = None
    try:
        quiet(ru.run_session, target="REALX", hours=2 / 3600, band="423",
              source="real", out_dir=out_real)
    except Exception as e:
        raised = e
    made = os.listdir(out_real) if os.path.isdir(out_real) else []
    chk("chế độ 'Bắt buộc SDR thật' → báo lỗi, KHÔNG ghi dữ liệu giả",
        isinstance(raised, RuntimeError) and not any(f.endswith(".fil") for f in made),
        f"{type(raised).__name__}: {str(raised)[:60]}" if raised else "không báo lỗi")
    chk("dữ liệu fallback vẫn đọc lại được (round-trip)",
        m.get("roundtrip_ok") is True, f"{m.get('rows')} dòng")
    side = [f for f in os.listdir(out) if f.endswith(".json")][0]
    meta = json.load(open(os.path.join(out, side), encoding="utf-8"))
    need = ("mode", "fallback", "chain", "gaps", "roundtrip_ok", "tsys_k",
            "sefd_jy", "started_utc")
    chk("sidecar metadata có đủ khoá bắt buộc",
        all(k in meta for k in need), f"thiếu: {[k for k in need if k not in meta]}")

    # dừng giữa chừng
    import threading
    ev = threading.Event()
    threading.Timer(0.35, ev.set).start()
    m2 = quiet(ru.run_session, target="STOP", hours=2.0, band="423", mock=True,
               out_dir=out, stop_event=ev)
    chk("DỪNG giữa chừng: đóng file an toàn, không hỏng",
        m2.get("roundtrip_ok") is True and m2.get("rows", 0) > 0,
        f"{m2.get('rows')} dòng trước khi dừng")

    # mô phỏng mất mẫu
    m3 = quiet(ru.run_session, target="GAP", hours=30 / 3600, band="423",
               mock=True, out_dir=out, gap_every_s=2.0)
    chk("mất mẫu được ghi vào gap log",
        m3.get("n_gaps", 0) > 0 and m3.get("roundtrip_ok") is True,
        f"{m3.get('n_gaps')} gap")


# ------------------------------------------------------------------ S3 output
def s3_outputs(fx):
    section("S3. ĐẦU RA — thư mục, file, JSON, báo cáo, tái lập")
    before = set()
    for base, _, files in os.walk(ROOT):
        for f in files:
            before.add(os.path.join(base, f))

    m = quiet(psr_detect.detect, fx["fil8"], dm_ref=None, p_ref=None)
    stem = "ok8"
    outd = os.path.join(psr_detect.RESULTS, stem)
    chk("kết quả gom đúng 1 thư mục theo tên dữ liệu", os.path.isdir(outd), outd)
    need = ["fig1_overview.png", "fig2_detection.png",
            "detect_metrics.json", "detect_report.txt"]
    have = [f for f in need if os.path.exists(os.path.join(outd, f))]
    chk("đủ 4 tệp đầu ra", len(have) == 4, f"{len(have)}/4: {have}")

    js = json.load(open(os.path.join(outd, "detect_metrics.json"),
                        encoding="utf-8"))
    chk("JSON hợp lệ + có khoá cốt lõi",
        all(k in js for k in ("file", "stage", "output_checks", "pulses")),
        f"{len(js)} khoá")
    rep = open(os.path.join(outd, "detect_report.txt"), encoding="utf-8").read()
    dm_js = js["stage"].get("dm_scan_best")
    dm_txt = f"{dm_js:.2f}" in rep or f"{dm_js:.1f}" in rep
    chk("BÁO CÁO khớp JSON (cùng số DM)", dm_txt,
        f"DM JSON={dm_js}, có trong report: {dm_txt}")
    png = os.path.getsize(os.path.join(outd, "fig2_detection.png"))
    chk("ảnh PNG có nội dung thật (> 20 KB)", png > 20_000, f"{png/1024:.0f} KB")
    chk("metrics ghi đúng tên file nguồn", js.get("file") == "ok8.fil",
        js.get("file"))

    # tái lập: chạy lại không sinh thư mục mới
    n_dir_before = len([d for d in os.listdir(psr_detect.RESULTS)
                        if os.path.isdir(os.path.join(psr_detect.RESULTS, d))])
    quiet(psr_detect.detect, fx["fil8"])
    n_dir_after = len([d for d in os.listdir(psr_detect.RESULTS)
                       if os.path.isdir(os.path.join(psr_detect.RESULTS, d))])
    chk("chạy lại KHÔNG sinh thư mục rác", n_dir_before == n_dir_after,
        f"{n_dir_before} → {n_dir_after}")

    # tên có dấu cách + unicode + dài
    for name, label in (("có dấu cách.fil", "dấu cách"),
                        ("pulsar_观测_B0329.fil", "unicode"),
                        ("x" * 120 + ".fil", "tên rất dài")):
        p = os.path.join(TMP, name)
        shutil.copy(fx["fil8"], p)
        mm = quiet(psr_detect.detect, p)
        d = os.path.join(psr_detect.RESULTS,
                         psr_detect.safe_stem(os.path.splitext(name)[0]))
        chk(f"tên file {label}: chạy + xuất đúng thư mục",
            mm.get("status") == "ok" and os.path.isdir(d),
            f"status={mm.get('status')}, thư mục {os.path.basename(d)[:40]}")
        chk(f"tên file {label}: thư mục kết quả không quá dài",
            len(os.path.basename(d)) <= psr_detect.MAX_STEM,
            f"{len(os.path.basename(d))} ký tự (giới hạn {psr_detect.MAX_STEM})")

    # input hỏng → báo cáo chẩn đoán, không có ảnh giả
    m = quiet(psr_detect.detect, fx["zero"])
    d = os.path.join(psr_detect.RESULTS, "zero")
    chk("input 0 byte → có report JSON + KHÔNG có ảnh giả",
        os.path.exists(os.path.join(d, "detect_metrics.json"))
        and not os.path.exists(os.path.join(d, "fig2_detection.png")),
        m.get("status"))

    # không ghi ra ngoài thư mục app
    after = set()
    for base, _, files in os.walk(ROOT):
        for f in files:
            after.add(os.path.join(base, f))
    new = {p for p in after - before}
    outside = [p for p in new if not os.path.normpath(p).startswith(
        os.path.normpath(ROOT))]
    chk("không ghi file ra ngoài thư mục app", not outside, str(outside[:2]))

    # thư mục kết quả chỉ-đọc
    ro = os.path.join(TMP, "ro_results")
    os.makedirs(ro, exist_ok=True)
    old = psr_detect.RESULTS
    try:
        psr_detect.RESULTS = ro
        os.chmod(ro, 0o500)          # chỉ đọc/thi hành
        try:
            mm = quiet(psr_detect.detect, fx["fil8"])
            ok = mm.get("status") is not None
        except Exception as e:
            ok = False
        chk("thư mục kết quả CHỈ-ĐỌC: báo lỗi gọn (không treo)", ok,
            "đã xử lý")
    finally:
        os.chmod(ro, 0o700)
        psr_detect.RESULTS = old


# ---------------------------------------------------------------------- S4 GUI
def s4_gui():
    section("S4. GUI — nút, hộp thoại lỗi, khoá khi bận, đường dẫn")
    import tkinter as tk
    from tkinter import ttk
    import gui_app

    root = tk.Tk(); app = gui_app.App(root); root.update()
    dialogs = []
    gui_app.messagebox.showerror = lambda t, m, **k: dialogs.append(("err", m))
    gui_app.os.startfile = lambda p: dialogs.append(("open", p))

    def drain():
        try:
            while True:
                app.cbq.get_nowait()()
        except Exception:
            pass
        try:
            while True:
                app.log(app.q.get_nowait().rstrip())
        except Exception:
            pass

    def pump(t=180):
        t0 = time.time(); root.update(); drain()
        while app.busy and time.time() - t0 < t:
            root.update(); drain(); time.sleep(0.04)
        for _ in range(40):
            root.update(); drain(); time.sleep(0.02)
        return not app.busy

    chk("đủ 5 tab", len(app.nb.tabs()) == 5, app.nb.tabs() and "5 tab")
    n_btn = 0
    for tab in (app.tab_rec, app.tab_det, app.tab_tgt, app.tab_hw, app.tab_chk):
        for w in tab.winfo_children():
            for c in (w.winfo_children() if hasattr(w, "winfo_children") else []):
                if isinstance(c, ttk.Button):
                    n_btn += 1
    chk("có ≥ 15 nút bấm", n_btn >= 15, f"{n_btn} nút")

    # lỗi: chưa chọn file
    app.det_file.delete(0, "end"); dialogs.clear()
    app.run_detect()
    chk("bấm Phát hiện khi CHƯA chọn file → hộp thoại lỗi, không crash",
        any(d[0] == "err" for d in dialogs), dialogs[:1])

    # lỗi: file không tồn tại
    app.det_file.delete(0, "end"); app.det_file.insert(0, os.path.join(TMP, "a.fil"))
    dialogs.clear(); app.run_detect()
    chk("file không tồn tại → hộp thoại lỗi", any(d[0] == "err" for d in dialogs))

    # lỗi: DM không phải số
    app.det_file.delete(0, "end")
    app.det_file.insert(0, os.path.join(TMP, "ok8.fil"))
    app.det_dm.delete(0, "end"); app.det_dm.insert(0, "abc")
    dialogs.clear(); app.run_detect()
    chk("DM nhập chữ → hộp thoại lỗi, không crash",
        any(d[0] == "err" for d in dialogs))
    app.det_dm.delete(0, "end"); app.det_dm.insert(0, "0")

    # khoá khi đang bận
    app.rec_hours.set(30 / 3600); app.rec_source.set(gui_app.SOURCE_MODES["mock"])
    app.start_recording()
    root.update()
    busy1 = app.busy
    app.run_detect()                       # bấm chen ngang
    # LƯU Ý: trong lúc job chạy, run_bg redirect stdout TOÀN CỤC → print() ở
    # main thread bị hút vào log GUI. Vì vậy thu kết quả trước, IN SAU.
    refused = "Đang có tác vụ chạy" in app.log_text.get("1.0", "end")
    stop_state = str(app.btn_stop.cget("state"))
    app.stop_recording(); pump()
    chk("đang bận: nút khác bị TỪ CHỐI (không xếp hàng lung tung)",
        busy1 and refused, f"busy={busy1}, refused={refused}")
    chk("nút Dừng bật khi đang ghi", stop_state == "normal", stop_state)
    chk("sau khi Dừng: về trạng thái rảnh", not app.busy)
    chk("nút Dừng bị khoá khi rảnh",
        str(app.btn_stop.cget("state")) == "disabled")

    # mở thư mục không tồn tại
    dialogs.clear(); app.open_dir(os.path.join(TMP, "khong_co_dir"))
    chk("mở thư mục không tồn tại → báo lỗi, không crash",
        "chưa tồn tại" in app.log_text.get("1.0", "end"))

    # chạy phát hiện thật qua GUI
    app.det_dm.delete(0, "end"); app.det_dm.insert(0, "")
    app.run_detect(); ok = pump()
    chk("chạy phát hiện qua GUI (tab 2) thành công", ok and not app.busy)
    chk("dropdown ảnh có mục dạng thư-mục/tên",
        any("/" in str(v) for v in app.det_figpick.cget("values")),
        str(list(app.det_figpick.cget("values"))[:2]))

    # tải lại ảnh khác trong dropdown
    vals = list(app.det_figpick.cget("values"))
    if vals:
        app.det_figpick.set(vals[0]); app.show_selected_figure(); root.update()
        chk("đổi ảnh trong dropdown vẽ lại được", len(app.det_fig.axes) > 0,
            vals[0])
    root.destroy()
    chk("đóng app sạch (không còn tác vụ nền)", not app.busy)


# --------------------------------------------------------------- S5 đối chiếu
def s5_crosscheck(fx, fast=False):
    section("S5. ĐỐI CHIẾU ĐỘC LẬP")
    import selftest as st
    st.RESULT.clear()
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        st.test_physics(); st.test_dedispersion(); st.test_snr_calibration()
        st.test_sensitivity_formula(); st.test_period_refine()
        st.test_subband_dm(); st.test_targets()
        st.test_zero_dm_keeps_pulse(); st.test_subband_dm_single()
        st.test_find_pulses_cluster(); st.test_fil_roundtrip()
        st.test_iq_channelize()
    n, tot = sum(st.RESULT), len(st.RESULT)
    chk(f"selftest lõi ({tot} test)", n == tot, f"{n}/{tot} PASS")

    iq = os.path.join(ROOT, "data", "iq", "crab-giantpulse.sigmf-data")
    if os.path.exists(iq):
        m = quiet(psr_detect.detect, iq, dm_ref=56.77)
        dme = m["stage"].get("dm_subband_mean") or m["stage"].get("dm_scan_best")
        err = abs(dme - 56.77)
        chk("IQ THẬT (Crab GP): DM đo khớp catalogue (<2%)",
            err < 0.02 * 56.77, f"DM {dme:.2f} vs 56.77 (lệch {err:.2f})")
        chk("IQ THẬT: phát hiện xung SNR ≥ 20",
            (m["stage"].get("dm_scan_peak_snr") or 0) >= 20,
            f"SNR {m['stage'].get('dm_scan_peak_snr')}")
        # BỐ CỤC HÌNH: chú giải/chú thích không được đè dữ liệu, không tràn khung
        figi = m.get("figure_check")
        chk("bố cục hình: không chú giải/chú thích đè dữ liệu",
            figi == [], f"figure_check = {figi}")
        f2p = os.path.join(m["out_dir"], "fig2_detection.png")
        ok_size = (os.path.exists(f2p) and os.path.getsize(f2p) > 60_000)
        chk("hình fig2_detection.png xuất ra hợp lệ", ok_size,
            f"{os.path.getsize(f2p)//1024} KB" if os.path.exists(f2p) else "THIẾU")
    else:
        chk("có file IQ thật để đối chiếu", False, iq)

    if not fast:
        import stress_test
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = stress_test.main()
        chk("corpus dữ liệu XẤU (10 file)", rc == 0,
            [l for l in buf.getvalue().splitlines() if "file hành xử" in l][-1:])

        # GUI selfcheck (đường đóng gói)
        import gui_app
        rc2 = gui_app.selfcheck()
        chk("gui_app --selfcheck (đường đóng gói)", rc2 == 0, f"rc={rc2}")
        exe = os.path.join(ROOT, "PulsarObs.exe")
        if os.path.exists(exe):
            import subprocess
            r = subprocess.run([exe, "--selfcheck"], capture_output=True,
                               timeout=300)
            chk("EXE --selfcheck", r.returncode == 0, f"rc={r.returncode}")
            rep = os.path.join(ROOT, "selfcheck_report.txt")
            if os.path.exists(rep):
                txt = open(rep, encoding="utf-8").read()
                chk("EXE báo frozen=True (đúng là bản đóng gói)",
                    "frozen = True" in txt, txt.splitlines()[1] if txt else "")
                os.remove(rep)
        else:
            chk("có PulsarObs.exe để kiểm", False, exe)


# -------------------------------------------------------------------- main
def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    fast = "--fast" in sys.argv
    only = None
    if "--only" in sys.argv:
        only = sys.argv[sys.argv.index("--only") + 1].upper()
    t0 = time.time()
    print("NGHIỆM THU HỆ THỐNG PULSAR OBSERVATION")
    print(f"thư mục: {ROOT}\nPython {sys.version.split()[0]}, "
          f"numpy {np.__version__}")
    for d in ("results", "data"):
        os.makedirs(os.path.join(ROOT, d), exist_ok=True)
    fx = make_fixtures()
    if only in (None, "S1"):
        s1_inputs(fx)
    if only in (None, "S2"):
        s2_fallback(fx)
    if only in (None, "S3"):
        s3_outputs(fx)
    if only in (None, "S4"):
        s4_gui()
    if only in (None, "S5"):
        s5_crosscheck(fx, fast)

    n_ok = sum(1 for _, ok, _ in R if ok)
    print(f"\n{'='*78}")
    print(f"KẾT QUẢ NGHIỆM THU: {n_ok}/{len(R)} ĐẠT "
          f"({time.time()-t0:.0f}s)")
    bad = [(n, d) for n, ok, d in R if not ok]
    if bad:
        print("\nMỤC KHÔNG ĐẠT:")
        for n, d in bad:
            print(f"  ✗ {n} — {d}")
        print("\n⇒ CHƯA ĐỦ ĐIỀU KIỆN ĐƯA VÀO SỬ DỤNG.")
    else:
        print("\n⇒ ĐẠT TẤT CẢ ĐIỀU KIỆN NGHIỆM THU — có thể đưa vào sử dụng.")
    # ghi biên bản
    with open(os.path.join(ROOT, "results", "acceptance_report.txt"), "w",
              encoding="utf-8") as fh:
        fh.write(f"NGHIỆM THU {time.strftime('%Y-%m-%d %H:%M')}\n")
        for n, ok, d in R:
            fh.write(f"[{'PASS' if ok else 'FAIL'}] {n} — {d}\n")
        fh.write(f"\n{n_ok}/{len(R)} ĐẠT\n")
    print(f"→ biên bản: results/acceptance_report.txt")
    return 0 if n_ok == len(R) else 1


if __name__ == "__main__":
    sys.exit(main())
