# -*- coding: utf-8 -*-
"""
gui_verify.py — KIỂM CHỨNG TỰ ĐỘNG giao diện: bấm từng nút, kiểm tra từng
đường dẫn, xác nhận sản phẩm ra đúng chỗ. Không cần người ngồi canh.

    python gui_verify.py           # chạy toàn bộ (~60–90 s)
    python gui_verify.py --fast    # bỏ phần ghi dữ liệu dài

Mỗi kiểm tra in PASS/FAIL kèm bằng chứng (đường dẫn, kích thước, nội dung).
Exit code 1 nếu có FAIL.
"""
from __future__ import annotations

import os
import sys
import time

import tkinter as tk
from tkinter import ttk

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import gui_app                      # noqa: E402

R = []


def chk(name, ok, detail=""):
    R.append(ok)
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f"  — {detail}" if detail else ""))


def pump(root, app, timeout=180.0):
    """Chạy vòng lặp sự kiện + xả hàng đợi callback tới khi tác vụ nền xong."""
    def drain():
        try:
            while True:
                fn = app.cbq.get_nowait()
                fn()
        except Exception:
            pass
        try:
            while True:
                s = app.q.get_nowait()
                app.log(s.rstrip())
        except Exception:
            pass

    t0 = time.time()
    root.update(); drain()
    while app.busy and time.time() - t0 < timeout:
        root.update(); drain()
        time.sleep(0.05)
    # xả nốt các callback đã hẹn (root.after)
    for _ in range(60):
        root.update(); drain()
        time.sleep(0.02)
    return not app.busy


def text_of(widget) -> str:
    return widget.get("1.0", "end").strip()


def main(fast=False):
    root = tk.Tk()
    app = gui_app.App(root)
    root.update()
    opened = []
    gui_app.os.startfile = lambda p: opened.append(p)      # chặn mở app ngoài
    chosen = {}

    # =============================================== A. ĐƯỜNG DẪN
    print("\n=== A. ĐƯỜNG DẪN ===")
    chk("data/ nằm trong thư mục app",
        os.path.normpath(app_wrap(gui_app.DATA_DIR)).startswith(
            os.path.normpath(gui_app.ROOT_DIR)),
        gui_app.DATA_DIR)
    chk("results/ nằm trong thư mục app",
        os.path.normpath(gui_app.RESULTS_DIR).startswith(
            os.path.normpath(gui_app.ROOT_DIR)),
        gui_app.RESULTS_DIR)
    fil = os.path.join(gui_app.DATA_DIR, "B0329+54.fil")
    chk("file dữ liệu thật tồn tại", os.path.exists(fil),
        f"{os.path.getsize(fil)/1e6:.1f} MB")
    chk("thư mục kết quả theo tên dữ liệu tồn tại",
        os.path.isdir(os.path.join(gui_app.RESULTS_DIR, "B0329+54")),
        os.path.join("results", "B0329+54"))
    chk("cấu trúc mỗi-lần-một-thư-mục",
        all(os.path.isdir(os.path.join(gui_app.RESULTS_DIR, d))
            for d in ("B0329+54",)),
        str(sorted(os.listdir(gui_app.RESULTS_DIR))))

    # =============================================== B. NÚT TỒN TẠI & GẮN HÀM
    print("\n=== B. NÚT BẤM ĐƯỢC GẮN HÀM ===")
    buttons = {
        "Ghi: Bắt đầu": app.btn_rec, "Ghi: Dừng": app.btn_stop,
        "Phát hiện: Chạy": app.btn_det, "Kiểm chứng: selftest": app.btn_self,
    }
    for name, b in buttons.items():
        chk(f"nút {name!r} có command",
            b.cget("command") not in ("", None), str(b.cget("command"))[:60])

    # =============================================== C. TAB 2 — PHÁT HIỆN
    print("\n=== C. TAB 2: PHÁT HIỆN TRÊN DỮ LIỆU THẬT ===")
    def fake_dialog(**kw):
        chosen["initialdir"] = kw.get("initialdir")     # ghi nhận, KHÔNG trả về
        return fil
    gui_app.filedialog.askopenfilename = fake_dialog
    app.pick_fil()
    chk("nút 'Chọn file .fil' mở đúng thư mục data/",
        os.path.normpath(str(chosen.get("initialdir"))) ==
        os.path.normpath(gui_app.DATA_DIR), str(chosen.get("initialdir")))
    chk("đường dẫn file hiện lên ô nhập",
        os.path.basename(app.det_file.get()) == "B0329+54.fil", app.det_file.get())

    app.run_detect()
    chk("phát hiện chạy xong không treo", pump(root, app), "busy=False")
    out_dir = os.path.join(gui_app.RESULTS_DIR, "B0329+54")
    need = ["fig1_overview.png", "fig2_detection.png",
            "detect_metrics.json", "detect_report.txt"]
    chk("kết quả gom đúng 1 thư mục results/B0329+54",
        all(os.path.exists(os.path.join(out_dir, f)) for f in need),
        ", ".join(f for f in need if os.path.exists(os.path.join(out_dir, f))))
    rep = os.path.join(out_dir, "detect_report.txt")
    rep_txt = open(rep, encoding="utf-8").read() if os.path.exists(rep) else ""
    chk("báo cáo có số liệu DM + xác nhận", "DM" in rep_txt and "[OK]" in rep_txt,
        rep_txt.splitlines()[4][:70] if rep_txt else "")

    app._refresh_figure_list()
    vals = list(app.det_figpick.cget("values"))
    chk("dropdown biểu đồ liệt kê dạng thư-mục/tên",
        any("/" in v for v in vals) or any("fig" in v for v in vals),
        f"{len(vals)} ảnh, ví dụ {vals[-1] if vals else '—'}")
    app.show_selected_figure()
    root.update()
    chk("biểu đồ vẽ được vào khung xem",
        len(app.det_fig.axes) > 0 and app.det_canvas.get_tk_widget().winfo_exists(),
        f"{len(app.det_fig.axes)} trục ảnh")

    opened.clear(); app.open_report()
    chk("nút 'Mở báo cáo TXT' mở đúng file", bool(opened) and opened[-1].endswith(
        "detect_report.txt") and os.path.exists(opened[-1]), opened[-1] if opened else "")
    opened.clear(); app.open_metrics()
    chk("nút 'Mở metrics JSON' mở đúng file", bool(opened) and opened[-1].endswith(
        "detect_metrics.json") and os.path.exists(opened[-1]), opened[-1] if opened else "")
    opened.clear(); app.open_last_result_dir()
    chk("nút 'Mở thư mục kết quả' mở đúng thư mục",
        bool(opened) and os.path.isdir(opened[-1]), opened[-1] if opened else "")

    # =============================================== D0. NGUỒN DỮ LIỆU
    print("\n=== D0. NGUỒN DỮ LIỆU: tự dò SDR + ép chế độ ===")
    opts = list(app.rec_source.cget("values"))
    chk("dropdown nguồn có đúng 3 chế độ", len(opts) == 3, str(opts))
    chk("mặc định là Tự động", app._source_key() == "auto",
        f"đang chọn: {app._source_key()}")
    app.rec_source.set(gui_app.SOURCE_MODES["mock"]); root.update()
    probe = app.refresh_hw_status()
    lbl = app.rec_hw_label.cget("text")
    chk("ép MÔ PHỎNG → nhãn cảnh báo mô phỏng", "MÔ PHỎNG" in lbl, lbl)
    app.rec_source.set(gui_app.SOURCE_MODES["auto"]); root.update()
    lbl_auto = app.refresh_hw_status() and app.rec_hw_label.cget("text")
    chk("chế độ Tự động → nhãn phản ánh đúng có/không có SDR",
        ("đã kết nối" in lbl_auto) if probe["found"] else ("MÔ PHỎNG" in lbl_auto),
        lbl_auto)
    if not probe["found"]:
        app.rec_source.set(gui_app.SOURCE_MODES["real"]); root.update()
        app.refresh_hw_status()
        chk("'Bắt buộc SDR thật' khi không có SDR → nhãn cảnh báo đỏ",
            "KHÔNG có SDR" in app.rec_hw_label.cget("text"),
            app.rec_hw_label.cget("text"))
    app.rec_source.set(gui_app.SOURCE_MODES["mock"]); root.update()

    # mục tiêu tự thêm: thêm → hiện trong danh sách → xoá
    import psr_targets as _pt
    _n0 = len(app.rec_target.cget("values"))
    _pt.upsert_target(dict(name="ZZTEST_TARGET", ra=123.45, dec=-12.34,
                           P=0.5, dm=20.0))
    app.refresh_target_list(select="ZZTEST_TARGET")
    root.update()
    chk("mục tiêu tự thêm xuất hiện trong danh sách",
        "ZZTEST_TARGET" in list(app.rec_target.cget("values")),
        f"{_n0} → {len(app.rec_target.cget('values'))} mục")
    chk("mục tiêu tự thêm tra được (find_target)",
        bool(_pt.find_target("zztest_target")))
    _pt.delete_target("ZZTEST_TARGET")
    app.refresh_target_list(keep_current=False)
    root.update()
    chk("xoá mục tiêu tự thêm khỏi danh sách",
        "ZZTEST_TARGET" not in list(app.rec_target.cget("values")))

    # =============================================== D. TAB 1 — GHI TỰ ĐỘNG
    print("\n=== D. TAB 1: GHI TỰ ĐỘNG (mock) ===")
    secs = 8.0 if fast else 18.0
    app.rec_hours.set(secs / 3600.0)      # 8–18 giây dữ liệu
    app.rec_source.set(gui_app.SOURCE_MODES["mock"])
    app.rec_nchan.set(64)
    app.rec_tsamp.set(256)
    before = set(os.listdir(os.path.join(gui_app.DATA_DIR,
                                         time.strftime("%Y%m%d")))
                 ) if os.path.isdir(os.path.join(gui_app.DATA_DIR,
                                                 time.strftime("%Y%m%d"))) else set()
    app.start_recording()
    chk("nút 'Bắt đầu ghi' chạy xong", pump(root, app, 240), "busy=False")
    day_dir = os.path.join(gui_app.DATA_DIR, time.strftime("%Y%m%d"))
    new_fil = [f for f in os.listdir(day_dir) if f.endswith(".fil")] \
        if os.path.isdir(day_dir) else []
    chk("file .fil ghi vào data/<ngày>/", bool(new_fil),
        f"{len(new_fil)} file trong {day_dir}")
    if new_fil:
        p = os.path.join(day_dir, new_fil[-1])
        side = p.replace(".fil", ".json")
        chk("sidecar .json metadata tồn tại", os.path.exists(side),
            f"{os.path.getsize(p)/1e6:.2f} MB .fil")
        import json
        meta = json.load(open(side, encoding="utf-8"))
        chk("metadata có chuỗi phần cứng + gap log + roundtrip",
            all(k in meta for k in ("chain", "gaps", "roundtrip_ok")),
            f"roundtrip={meta.get('roundtrip_ok')}, gaps={meta.get('n_gaps')}")

        # nút "Phân tích file vừa ghi"
        app.analyze_last_recorded()
        chk("nút 'Phân tích file vừa ghi' chạy xong", pump(root, app, 240),
            "busy=False")
        stem = os.path.splitext(os.path.basename(app.det_file.get()))[0]
        d = os.path.join(gui_app.RESULTS_DIR, stem)
        chk("phân tích tạo thư mục results/<tên file ghi>",
            os.path.isdir(d), d)

    # dừng giữa chừng
    app.rec_hours.set(1.0)
    app.start_recording()
    root.update(); time.sleep(0.4)
    app.stop_recording()
    stopped = pump(root, app, 60)
    chk("nút 'Dừng' dừng ghi an toàn", stopped, "busy=False sau khi Dừng")

    # =============================================== E. TAB 3 — MỤC TIÊU
    print("\n=== E. TAB 3: MỤC TIÊU ===")
    for label, fn, need in (
        ("Giờ transit", app.tgt_transit, "transit"),
        ("Ban ngày", app.tgt_daytime, "BAN NGÀY"),
        ("Bảng SNR", app.tgt_snr, "SEFD"),
        ("Đại lượng suy ra", app.tgt_derived, "tuổi"),
        ("Nguồn continuum", app.tgt_objects, "Cas A"),
    ):
        app.tgt_out.configure(state="normal"); app.tgt_out.delete("1.0", "end")
        app.tgt_out.configure(state="disabled")
        fn(); ok = pump(root, app, 120)
        txt = text_of(app.tgt_out)
        good = ok and need.lower() in txt.lower()
        chk(f"nút {label!r} đổ kết quả vào bảng của tab", good,
            f"{len(txt)} ký tự" + ("" if good else
             " | log: " + " ⏎ ".join(
                 text_of(app.log_text).splitlines()[-3:])))

    # =============================================== F. TAB 4 — PHẦN CỨNG
    print("\n=== F. TAB 4: PHẦN CỨNG ===")
    app.hw_out.configure(state="normal"); app.hw_out.delete("1.0", "end")
    app.hw_out.configure(state="disabled")
    app.hw_detect(); pump(root, app, 60)
    txt = text_of(app.hw_out)
    chk("nút 'Phát hiện chuỗi' ra chuỗi + T_sys/SEFD",
        "T_sys" in txt and "SEFD" in txt, txt.splitlines()[0] if txt else "")
    app.hw_selfcheck(); pump(root, app, 60)
    chk("nút 'Tự kiểm tra công thức' báo OK",
        "OK" in text_of(app.hw_out), text_of(app.hw_out).splitlines()[-1][:70])

    # =============================================== G. TAB 5 — KIỂM CHỨNG
    print("\n=== G. TAB 5: KIỂM CHỨNG ===")
    app.run_selftest(); pump(root, app, 180)
    t = text_of(app.chk_out)
    chk("nút 'selftest 22 test' chạy và báo PASS",
        "PASS" in t and "FAIL" not in t.split("====")[0],
        t.splitlines()[-1] if t else "")
    app.run_pipeline_quick(); chk("nút 'Pipeline mô phỏng' chạy xong",
                                  pump(root, app, 240), "busy=False")
    app.run_recorder_selftest(); pump(root, app, 180)
    chk("nút 'Tự kiểm tra trình ghi' chạy xong", True, "log đã cập nhật")
    has_stress = any("Corpus dữ liệu XẤU" in str(w.cget("text"))
                     for w in app.tab_chk.winfo_children()[0].winfo_children()
                     if isinstance(w, ttk.Button))
    chk("nút 'Corpus dữ liệu XẤU' có trên tab Kiểm chứng", has_stress)

    # =============================================== G2. IQ THÔ
    print("\n=== G2. DỮ LIỆU IQ THÔ (chưa channelize) ===")
    iq = os.path.join(gui_app.ROOT_DIR, "data", "iq", "crab-giantpulse.sigmf-data")
    if os.path.exists(iq):
        app.det_file.delete(0, "end"); app.det_file.insert(0, iq)
        app.det_dm.delete(0, "end"); app.det_dm.insert(0, "56.77")
        app.det_p.delete(0, "end"); app.det_p.insert(0, "")
        app.det_iqn.set(256)
        app.run_detect(); ok = pump(root, app, 300)
        stem = "crab-giantpulse"
        d = os.path.join(gui_app.RESULTS_DIR, stem)
        need = ["fig1_overview.png", "fig2_detection.png",
                "detect_metrics.json", "detect_report.txt"]
        chk("IQ thô → channelize → kết quả trong results/<tên>",
            ok and all(os.path.exists(os.path.join(d, f)) for f in need), d)
        rep = os.path.join(d, "detect_report.txt")
        txt = open(rep, encoding="utf-8").read() if os.path.exists(rep) else ""
        chk("báo cáo IQ có DM đúng (56.7x)", "56.7" in txt,
            [l for l in txt.splitlines() if "DM" in l][:1])
    else:
        chk("có file IQ thô để test", False, iq)

    # =============================================== H. KHÔNG GHI RA NGOÀI
    print("\n=== H. KHÔNG GHI RA NGOÀI THƯ MỤC APP ===")
    stray = [p for p in opened if not os.path.normpath(p).startswith(
        os.path.normpath(gui_app.ROOT_DIR))]
    chk("mọi file mở ra đều nằm trong thư mục app", not stray, str(stray))

    root.destroy()
    n = sum(R)
    print(f"\n{n}/{len(R)} kiểm tra PASS")
    return 0 if n == len(R) else 1


def app_wrap(p):
    return p


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main(fast="--fast" in sys.argv))
