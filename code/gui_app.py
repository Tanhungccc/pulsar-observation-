# -*- coding: utf-8 -*-
"""
gui_app.py — GIAO DIỆN MÁY TÍNH ĐỂ BÀN cho chương trình Pulsar Observation.

Bọc toàn bộ công cụ đã có trong một cửa sổ 5 tab:
    1. GHI TỰ ĐỘNG   — record_unattended (4–5 giờ, không cần canh chừng)
    2. PHÁT HIỆN      — psr_detect trên file .fil thật (số liệu + biểu đồ)
    3. MỤC TIÊU       — psr_targets: transit, ban ngày, bảng SNR, đại lượng
    4. PHẦN CỨNG      — psr_hw: chuỗi linh kiện, fallback, T_sys/SEFD
    5. KIỂM CHỨNG     — selftest 22 test + pipeline mô phỏng + mở thư mục

Chạy trực tiếp:   python gui_app.py
Đóng gói EXE:     build_exe.bat   (tạo PulsarObs.exe một-click)
Kiểm tra EXE:     PulsarObs.exe --selfcheck  (ghi selfcheck_report.txt)

Không cần Tkinter bên thứ ba; hiển thị biểu đồ bằng matplotlib (không dùng
pyplot để không xung đột backend với Agg khi ghi hình).
"""
from __future__ import annotations

import contextlib
import os
import queue
import sys
import threading
import traceback
from datetime import datetime

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

# ---------------------------------------------------------------- đường dẫn
FROZEN = getattr(sys, "frozen", False)
if FROZEN:
    APP_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    APP_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = APP_DIR if FROZEN else os.path.dirname(APP_DIR)
CODE_DIR = APP_DIR
DATA_DIR = os.path.join(ROOT_DIR, "data")
RESULTS_DIR = os.path.join(ROOT_DIR, "results")

sys.path.insert(0, CODE_DIR)


def asset_path(name: str) -> str | None:
    """Tìm file trong assets/ — chạy từ mã nguồn hoặc từ EXE đã đóng gói."""
    cands = [os.path.join(APP_DIR, "assets", name),
             os.path.join(ROOT_DIR, "assets", name)]
    base = getattr(sys, "_MEIPASS", None)
    if base:
        cands.insert(0, os.path.join(base, "assets", name))
    for c in cands:
        if os.path.exists(c):
            return c
    return None


def apply_icon(root) -> str:
    """Gắn icon cho cửa sổ + taskbar Windows. Trả về mô tả để selfcheck ghi lại."""
    info = []
    # Windows: tách tiến trình khỏi python.exe để taskbar dùng icon riêng
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "PulsarObs.RTP37")
        info.append("AppUserModelID=ok")
    except Exception:
        pass
    ico = asset_path("icon.ico")
    if ico:
        try:
            root.iconbitmap(default=ico)
            info.append(f"iconbitmap={os.path.basename(ico)}")
        except Exception as e:
            info.append(f"iconbitmap lỗi: {e!r}")
    png = asset_path("icon.png")
    if png:
        try:
            from tkinter import PhotoImage
            img = PhotoImage(file=png)
            root.iconphoto(True, img)
            root._icon_ref = img          # giữ tham chiếu, nếu không sẽ mất
            info.append(f"iconphoto={os.path.basename(png)}")
        except Exception as e:
            info.append(f"iconphoto lỗi: {e!r}")
    return "; ".join(info) if info else "không có icon"

# ép module dùng đúng thư mục data/results (không phụ thuộc nơi khởi chạy)
import psr_detect            # noqa: E402
import record_unattended     # noqa: E402
import psr_targets           # noqa: E402
psr_detect.RESULTS = RESULTS_DIR
psr_detect.DATA = DATA_DIR
record_unattended.DATA = DATA_DIR
psr_targets.RESULTS = RESULTS_DIR


# ---------------------------------------------------------------- log an toàn
class QueueWriter:
    """Thay sys.stdout/stderr: đẩy chuỗi vào queue để UI tự vẽ (thread-safe)."""

    def __init__(self, q: queue.Queue):
        self.q = q

    def write(self, s):
        if s and s.strip():
            self.q.put(str(s))

    def flush(self):
        pass


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Pulsar Observation — POAM RTP-3.7 (TP.HCM)")
        self.icon_info = apply_icon(self.root)
        self.root.geometry("1100x780")
        self.root.minsize(900, 620)

        self.q: queue.Queue = queue.Queue()      # chuỗi log từ thread phụ
        self.cbq: queue.Queue = queue.Queue()    # callable cần chạy ở MAIN thread
        self.writer = QueueWriter(self.q)
        self.busy = False
        self.stop_event = threading.Event()
        self.worker: threading.Thread | None = None

        self._build_style()
        self._build_layout()
        self._poll_queue()
        self.log("Sẵn sàng. Chọn tab để bắt đầu.")
        self.log(f"Thư mục dữ liệu: {DATA_DIR}")
        self.log(f"Thư mục kết quả: {RESULTS_DIR}")

    # ------------------------------------------------------------ giao diện
    def _build_style(self):
        st = ttk.Style()
        if "vista" in st.theme_names():
            st.theme_use("vista")
        st.configure("TLabelframe.Label", font=("Segoe UI", 10, "bold"))
        st.configure("TButton", font=("Segoe UI", 9))
        st.configure("TLabel", font=("Segoe UI", 9))

    def _build_layout(self):
        self.nb = ttk.Notebook(self.root)
        self.nb.pack(fill="both", expand=True, padx=6, pady=6)

        self.tab_rec = ttk.Frame(self.nb)
        self.tab_det = ttk.Frame(self.nb)
        self.tab_tgt = ttk.Frame(self.nb)
        self.tab_hw = ttk.Frame(self.nb)
        self.tab_chk = ttk.Frame(self.nb)
        self.nb.add(self.tab_rec, text="  1 · GHI TỰ ĐỘNG  ")
        self.nb.add(self.tab_det, text="  2 · PHÁT HIỆN  ")
        self.nb.add(self.tab_tgt, text="  3 · MỤC TIÊU  ")
        self.nb.add(self.tab_hw, text="  4 · PHẦN CỨNG  ")
        self.nb.add(self.tab_chk, text="  5 · KIỂM CHỨNG  ")

        self._build_recorder_tab()
        self._build_detect_tab()
        self._build_targets_tab()
        self._build_hw_tab()
        self._build_check_tab()

        # ---- khung log chung (dưới cùng)
        lf = ttk.LabelFrame(self.root, text="Nhật ký")
        lf.pack(fill="both", expand=False, padx=6, pady=(0, 6))
        self.log_text = tk.Text(lf, height=10, wrap="word",
                                font=("Consolas", 9), state="disabled",
                                bg="#111", fg="#d8d8d8")
        sb = ttk.Scrollbar(lf, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=sb.set)
        self.log_text.pack(side="left", fill="both", expand=True, padx=4, pady=4)
        sb.pack(side="right", fill="y")
        self.log_text.tag_configure("err", foreground="#ff8a8a")
        self.log_text.tag_configure("ok", foreground="#8affa0")

    # ---- TAB 1: ghi tự động
    def _build_recorder_tab(self):
        f = ttk.LabelFrame(self.tab_rec,
                           text="Ghi phổ động (dynamic spectrum) — 4–5 giờ, không cần canh chừng")
        f.pack(fill="x", padx=8, pady=8)

        ttk.Label(f, text="Mục tiêu:").grid(row=0, column=0, sticky="w", padx=4, pady=4)
        names = [t["name"] for t in psr_targets.PULSARS]
        self.rec_target = ttk.Combobox(f, values=names, width=16)
        self.rec_target.set("B0950+08")
        self.rec_target.grid(row=0, column=1, padx=4, pady=4)

        ttk.Label(f, text="Băng (MHz):").grid(row=0, column=2, sticky="w", padx=4)
        self.rec_band = ttk.Combobox(f, values=["423", "1420"], width=6)
        self.rec_band.set("423")
        self.rec_band.grid(row=0, column=3, padx=4)

        ttk.Label(f, text="Thời lượng (giờ):").grid(row=0, column=4, sticky="w", padx=4)
        self.rec_hours = ttk.Spinbox(f, from_=0.5, to=8.0, increment=0.5, width=6)
        self.rec_hours.set(4.5)
        self.rec_hours.grid(row=0, column=5, padx=4)

        ttk.Label(f, text="Kênh:").grid(row=1, column=0, sticky="w", padx=4)
        self.rec_nchan = ttk.Spinbox(f, from_=16, to=512, increment=16, width=6)
        self.rec_nchan.set(64)
        self.rec_nchan.grid(row=1, column=1, padx=4, sticky="w")

        ttk.Label(f, text="tsamp (µs):").grid(row=1, column=2, sticky="w", padx=4)
        self.rec_tsamp = ttk.Spinbox(f, from_=64, to=2000, increment=64, width=6)
        self.rec_tsamp.set(256)
        self.rec_tsamp.grid(row=1, column=3, padx=4, sticky="w")

        self.rec_mock = tk.BooleanVar(value=True)
        ttk.Checkbutton(f, text="Chế độ MÔ PHỎNG (không cần SDR — dùng khi chưa cắm thiết bị)",
                        variable=self.rec_mock).grid(row=1, column=4, columnspan=2,
                                                     sticky="w", padx=4)

        bf = ttk.Frame(self.tab_rec)
        bf.pack(fill="x", padx=8)
        self.btn_rec = ttk.Button(bf, text="▶ Bắt đầu ghi", command=self.start_recording)
        self.btn_rec.pack(side="left", padx=4, pady=4)
        self.btn_stop = ttk.Button(bf, text="■ Dừng", command=self.stop_recording,
                                   state="disabled")
        self.btn_stop.pack(side="left", padx=4)
        ttk.Button(bf, text="Phân tích file vừa ghi",
                   command=self.analyze_last_recorded).pack(side="left", padx=4)
        ttk.Button(bf, text="Mở thư mục dữ liệu",
                   command=lambda: self.open_dir(DATA_DIR)).pack(side="left", padx=4)

        info = ttk.LabelFrame(self.tab_rec, text="Cách dùng")
        info.pack(fill="both", expand=True, padx=8, pady=8)
        ttk.Label(info, justify="left", wraplength=1000, text=(
            "· Trước khi treo chảo: python psr_targets.py --transit (hoặc tab 3) để biết giờ transit.\n"
            "· Bật MÔ PHỎNG khi chưa cắm RTL-SDR: toàn bộ chuỗi ghi/đọc/phát hiện vẫn chạy để kiểm chứng.\n"
            "· Khi có SDR thật: bỏ tick mô phỏng, chương trình tự phát hiện thiết bị và tự fallback linh kiện.\n"
            "· File ghi: data/<ngày>/<target>_<UTC>.fil + .json (metadata: chuỗi phần cứng, ppm, gap log).\n"
            "· Sáng hôm sau: sang tab 2 chọn file .fil → PHÁT HIỆN để ra báo cáo + biểu đồ."
        )).pack(anchor="w", padx=8, pady=8)

    # ---- TAB 2: phát hiện
    def _build_detect_tab(self):
        f = ttk.LabelFrame(self.tab_det, text="Phát hiện pulsar trên file filterbank (.fil)")
        f.pack(fill="x", padx=8, pady=8)

        ttk.Button(f, text="Chọn file .fil…", command=self.pick_fil).grid(
            row=0, column=0, padx=4, pady=4)
        self.det_file = ttk.Entry(f, width=64)
        self.det_file.grid(row=0, column=1, columnspan=3, padx=4, sticky="we")

        ttk.Label(f, text="DM tham chiếu:").grid(row=1, column=0, sticky="w", padx=4)
        self.det_dm = ttk.Entry(f, width=12)
        self.det_dm.insert(0, "26.7641")
        self.det_dm.grid(row=1, column=1, padx=4, sticky="w")

        ttk.Label(f, text="IQ → kênh:").grid(row=1, column=2, sticky="w", padx=4)
        self.det_p = ttk.Entry(f, width=10)
        self.det_p.insert(0, "0.714519699557")
        self.det_p.grid(row=1, column=3, padx=4, sticky="w")
        self.det_iqn = ttk.Spinbox(f, from_=32, to=2048, increment=64, width=6)
        self.det_iqn.set(256)
        self.det_iqn.grid(row=1, column=4, padx=4, sticky="w")

        bf = ttk.Frame(self.tab_det)
        bf.pack(fill="x", padx=8)
        self.btn_det = ttk.Button(bf, text="▶ Chạy phát hiện", command=self.run_detect)
        self.btn_det.pack(side="left", padx=4, pady=4)
        ttk.Button(bf, text="Mở báo cáo TXT",
                   command=self.open_report).pack(side="left", padx=4)
        ttk.Button(bf, text="Mở metrics JSON",
                   command=self.open_metrics).pack(side="left", padx=4)
        ttk.Button(bf, text="Mở thư mục kết quả của lần chạy",
                   command=self.open_last_result_dir).pack(side="left", padx=4)

        # ---- hiển thị biểu đồ
        vf = ttk.LabelFrame(self.tab_det, text="Biểu đồ kết quả")
        vf.pack(fill="both", expand=True, padx=8, pady=8)
        top = ttk.Frame(vf)
        top.pack(fill="x")
        ttk.Label(top, text="Hình:").pack(side="left", padx=4)
        self.det_figpick = ttk.Combobox(top, values=[], width=42)
        self.det_figpick.pack(side="left", padx=4)
        self.det_figpick.bind("<<ComboboxSelected>>", self.show_selected_figure)
        ttk.Button(top, text="Mở bằng trình xem ảnh",
                   command=self.open_figure_external).pack(side="left", padx=4)

        from matplotlib.figure import Figure
        from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
        self.det_fig = Figure(figsize=(9, 5.2))
        self.det_canvas = FigureCanvasTkAgg(self.det_fig, master=vf)
        self.det_canvas.get_tk_widget().pack(fill="both", expand=True)
        self._refresh_figure_list()

    # ---- TAB 3: mục tiêu
    def _build_targets_tab(self):
        f = ttk.LabelFrame(self.tab_tgt, text="Khả năng quan sát từ TP.HCM (lat 10.78°N)")
        f.pack(fill="x", padx=8, pady=8)
        ttk.Label(f, text="Ngày (YYYY-MM-DD, bỏ trống = hôm nay):").grid(
            row=0, column=0, padx=4, pady=4, sticky="w")
        self.tgt_date = ttk.Entry(f, width=12)
        self.tgt_date.grid(row=0, column=1, padx=4)
        ttk.Label(f, text="Băng thông (MHz):").grid(row=0, column=2, padx=4)
        self.tgt_bw = ttk.Spinbox(f, from_=2.4, to=56, increment=1.0, width=6)
        self.tgt_bw.set(20)
        self.tgt_bw.grid(row=0, column=3, padx=4)

        bf = ttk.Frame(self.tab_tgt)
        bf.pack(fill="x", padx=8)
        for txt, cmd in (("Giờ transit (để chảo cố định)", self.tgt_transit),
                         ("Quan sát ban ngày", self.tgt_daytime),
                         ("Bảng SNR 10 pulsar × 5 cấu hình", self.tgt_snr),
                         ("Đại lượng suy ra (B, tuổi, Ė)", self.tgt_derived),
                         ("Nguồn continuum khác", self.tgt_objects)):
            ttk.Button(bf, text=txt, command=cmd).pack(side="left", padx=4, pady=4)

        lf = ttk.LabelFrame(self.tab_tgt, text="Bảng kết quả")
        lf.pack(fill="both", expand=True, padx=8, pady=8)
        self.tgt_out = tk.Text(lf, wrap="none", font=("Consolas", 9),
                               state="disabled")
        sb1 = ttk.Scrollbar(lf, command=self.tgt_out.yview)
        sb2 = ttk.Scrollbar(lf, command=self.tgt_out.xview, orient="horizontal")
        self.tgt_out.configure(yscrollcommand=sb1.set, xscrollcommand=sb2.set)
        self.tgt_out.pack(side="top", fill="both", expand=True)
        sb1.pack(side="right", fill="y")

    # ---- TAB 4: phần cứng
    def _build_hw_tab(self):
        f = ttk.LabelFrame(self.tab_hw, text="Dự đoán chuỗi linh kiện + tự fallback")
        f.pack(fill="x", padx=8, pady=8)
        ttk.Label(f, text="Băng:").grid(row=0, column=0, padx=4, pady=4)
        self.hw_band = ttk.Combobox(f, values=["423", "1420"], width=6)
        self.hw_band.set("423")
        self.hw_band.grid(row=0, column=1, padx=4)
        ttk.Label(f, text="Mục đích:").grid(row=0, column=2, padx=4)
        self.hw_goal = ttk.Combobox(f, values=["pulsar", "hi", "unattended"],
                                    width=12)
        self.hw_goal.set("pulsar")
        self.hw_goal.grid(row=0, column=3, padx=4)
        ttk.Button(f, text="Phát hiện chuỗi", command=self.hw_detect).grid(
            row=0, column=4, padx=8)
        ttk.Button(f, text="Tự kiểm tra công thức", command=self.hw_selfcheck).grid(
            row=0, column=5, padx=4)

        lf = ttk.LabelFrame(self.tab_hw, text="Kết quả")
        lf.pack(fill="both", expand=True, padx=8, pady=8)
        self.hw_out = tk.Text(lf, wrap="none", font=("Consolas", 9),
                              state="disabled")
        sb = ttk.Scrollbar(lf, command=self.hw_out.yview)
        self.hw_out.configure(yscrollcommand=sb.set)
        self.hw_out.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

    # ---- TAB 5: kiểm chứng
    def _build_check_tab(self):
        f = ttk.LabelFrame(self.tab_chk, text="Kiểm chứng máy móc (chạy trước khi tin kết quả)")
        f.pack(fill="x", padx=8, pady=8)
        self.btn_self = ttk.Button(f, text="▶ Chạy selftest nhanh (21 test)",
                                   command=self.run_selftest)
        self.btn_self.pack(side="left", padx=6, pady=6)
        ttk.Button(f, text="Pipeline mô phỏng (nhanh)",
                   command=self.run_pipeline_quick).pack(side="left", padx=6)
        ttk.Button(f, text="Tự kiểm tra trình ghi (mock)",
                   command=self.run_recorder_selftest).pack(side="left", padx=6)
        ttk.Button(f, text="▶ Corpus dữ liệu XẤU (data/stress)",
                   command=self.run_stress).pack(side="left", padx=6)
        ttk.Button(f, text="Mở thư mục kết quả",
                   command=lambda: self.open_dir(RESULTS_DIR)).pack(side="left", padx=6)
        ttk.Button(f, text="Mở tài liệu docs",
                   command=lambda: self.open_dir(os.path.join(ROOT_DIR, "docs"))
                   ).pack(side="left", padx=6)

        lf = ttk.LabelFrame(self.tab_chk, text="Kết quả kiểm chứng")
        lf.pack(fill="both", expand=True, padx=8, pady=8)
        self.chk_out = tk.Text(lf, wrap="none", font=("Consolas", 9),
                               state="disabled")
        sb = ttk.Scrollbar(lf, command=self.chk_out.yview)
        self.chk_out.configure(yscrollcommand=sb.set)
        self.chk_out.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

    # ------------------------------------------------------------ tiện ích UI
    def log(self, msg: str, tag: str = ""):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", f"[{datetime.now():%H:%M:%S}] {msg}\n", tag)
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def out(self, widget, msg):
        widget.configure(state="normal")
        widget.insert("end", msg + "\n")
        widget.see("end")
        widget.configure(state="disabled")

    def post(self, fn):
        """Đưa callable vào hàng đợi để MAIN THREAD thực thi.

        Tkinter KHÔNG thread-safe: gọi root.after() từ thread phụ có thể ném
        'main thread is not in main loop' và làm sập app. Vì vậy mọi tương tác
        widget từ thread phụ phải đi qua post(); vòng poll (main thread) sẽ chạy.
        """
        self.cbq.put(fn)

    def _poll_queue(self):
        try:
            while True:
                s = self.q.get_nowait()
                self.log(s.rstrip())
        except queue.Empty:
            pass
        try:
            while True:
                fn = self.cbq.get_nowait()
                try:
                    fn()
                except Exception as e:
                    self.log(f"Lỗi xử lý callback UI: {e!r}", "err")
        except queue.Empty:
            pass
        self.root.after(120, self._poll_queue)

    def run_bg(self, fn, *args, on_done=None, **kwargs):
        """Chạy hàm nặng trong thread; log tự động; khoá nút khi đang chạy."""
        if self.busy:
            self.log("Đang có tác vụ chạy — đợi hoàn tất trước.", "err")
            return
        self.busy = True
        self._set_busy(True)
        self.stop_event = threading.Event()

        def wrapper():
            err = None
            with contextlib.redirect_stdout(self.writer), \
                 contextlib.redirect_stderr(self.writer):
                try:
                    fn(*args, **kwargs)
                except Exception as e:
                    err = e
                    traceback.print_exc()
            def done():
                self.busy = False
                self._set_busy(False)
                if err:
                    self.log(f"Tác vụ kết thúc với lỗi: {err!r}", "err")
                else:
                    self.log("✔ Tác vụ hoàn tất.", "ok")
                if on_done:
                    on_done()
            self.post(done)

        self.worker = threading.Thread(target=wrapper, daemon=True)
        self.worker.start()

    def _set_busy(self, busy: bool):
        state = "disabled" if busy else "normal"
        for b in (self.btn_rec, self.btn_det, self.btn_self):
            b.configure(state=state)
        self.btn_stop.configure(state="normal" if busy else "disabled")

    def run_into(self, widget, fn, clear=True):
        """Chạy fn trong thread nền, gom stdout ĐỔ VÀO widget của tab (không
        phải nhật ký chung) — đúng như người dùng mong đợi khi bấm nút."""
        if clear:
            widget.configure(state="normal")
            widget.delete("1.0", "end")
            widget.configure(state="disabled")

        def job():
            buf = []

            class W:
                def write(self, x):
                    if x and x.strip():
                        buf.append(str(x))
                def flush(self):
                    pass

            with contextlib.redirect_stdout(W()):
                fn()
            txt = "\n".join(buf)

            def draw():
                widget.configure(state="normal")
                widget.insert("end", txt + "\n")
                widget.see("end")
                widget.configure(state="disabled")
            self.post(draw)
        self.run_bg(job)

    def open_dir(self, path):
        """Mở thư mục — KHÔNG tự tạo (tránh sinh thư mục rác khi bấm nhầm)."""
        if not os.path.isdir(path):
            self.log(f"Thư mục chưa tồn tại: {path}", "err")
            return
        os.startfile(path)                      # Windows

    # ------------------------------------------------------------ TAB 1 actions
    def start_recording(self):
        try:
            hours = float(self.rec_hours.get())
            nchan = int(self.rec_nchan.get())
            tsamp = float(self.rec_tsamp.get())
        except ValueError:
            messagebox.showerror("Lỗi", "Giờ/kênh/tsamp phải là số")
            return
        mock = self.rec_mock.get()
        target = self.rec_target.get()
        band = self.rec_band.get()
        self.log(f"Bắt đầu ghi: {target} @ {band} MHz, {hours} h, "
                 f"{nchan} kênh × {tsamp:.0f} µs, mock={mock}")

        def job():
            record_unattended.run_session(
                target=target, hours=hours, band=band, mock=mock,
                nchan=nchan, tsamp_us=tsamp,
                out_dir=os.path.join(DATA_DIR, datetime.now().strftime("%Y%m%d")),
                stop_event=self.stop_event)
        self.run_bg(job, on_done=self._refresh_figure_list)

    def stop_recording(self):
        self.stop_event.set()
        self.log("Yêu cầu DỪNG — chờ file đóng an toàn…")

    def analyze_last_recorded(self):
        # tìm file .fil mới nhất trong data/
        newest = None
        for base, _, files in os.walk(DATA_DIR):
            for f in files:
                if f.endswith(".fil"):
                    p = os.path.join(base, f)
                    if newest is None or os.path.getmtime(p) > os.path.getmtime(newest):
                        newest = p
        if newest is None:
            self.log("Chưa có file .fil nào trong data/ — hãy ghi thử trước.", "err")
            return
        self.det_file.delete(0, "end")
        self.det_file.insert(0, newest)
        self.log(f"Chọn file mới nhất: {newest}")
        self.run_detect()

    # ------------------------------------------------------------ TAB 2 actions
    def pick_fil(self):
        p = filedialog.askopenfilename(
            initialdir=DATA_DIR,
            title="Chọn dữ liệu: filterbank .fil | PSRFITS .fits | IQ thô (SigMF/.cu8/.wav)",
            filetypes=[("Tất cả dữ liệu hỗ trợ",
                        "*.fil *.fits *.sigmf-data *.cu8 *.cs8 *.cs16 *.ci16 "
                        "*.cf32 *.iq *.wav"),
                       ("SIGPROC filterbank", "*.fil"),
                       ("PSRFITS", "*.fits"),
                       ("IQ thô (SigMF)", "*.sigmf-data"),
                       ("IQ thô (SDR)", "*.cu8 *.cs8 *.cs16 *.cf16 *.cf32 *.iq"),
                       ("Tất cả", "*.*")])
        if p:
            self.det_file.delete(0, "end")
            self.det_file.insert(0, p)
            stem = os.path.splitext(os.path.basename(p))[0]
            self._refresh_figure_list()
            self.log(f"Đã chọn: {p} (nhớ nhập DM/P tham chiếu cho {stem})")

    def run_detect(self):
        path = self.det_file.get().strip()
        if not path or not os.path.exists(path):
            messagebox.showerror("Lỗi", "Chưa chọn file .fil hợp lệ")
            return
        try:
            dm = float(self.det_dm.get()) if self.det_dm.get().strip() else None
            p = float(self.det_p.get()) if self.det_p.get().strip() else None
        except ValueError:
            messagebox.showerror("Lỗi", "DM/P phải là số")
            return

        try:
            nchan_iq = int(self.det_iqn.get())
        except Exception:
            nchan_iq = 256

        def job():
            psr_detect.load_any.__defaults__      # giữ chữ ký cũ
            psr_detect.detect(path, dm_ref=dm, p_ref=p, nchan_iq=nchan_iq)
        self.run_bg(job, on_done=self._after_detect)

    def _after_detect(self):
        self._refresh_figure_list()
        stem = os.path.splitext(os.path.basename(self.det_file.get().strip()))[0]
        cand = f"{stem}/fig2_detection.png"
        if cand in self.det_figpick.cget("values"):
            self.det_figpick.set(cand)
            self.show_selected_figure()

    def _refresh_figure_list(self):
        """Liệt kê ảnh dạng '<thư mục con>/<tên>.png' — mỗi lần chạy một thư mục."""
        figs = []
        if os.path.isdir(RESULTS_DIR):
            for d in sorted(os.listdir(RESULTS_DIR)):
                sub = os.path.join(RESULTS_DIR, d)
                if os.path.isdir(sub):
                    figs += [f"{d}/{f}" for f in sorted(os.listdir(sub))
                             if f.endswith(".png")]
            # ảnh cũ nằm rời trong results/ (bản trước) vẫn hiện được
            figs += sorted(f for f in os.listdir(RESULTS_DIR)
                           if f.endswith(".png"))
        self.det_figpick.configure(values=figs)
        if figs and not self.det_figpick.get():
            self.det_figpick.set(figs[-1])
            self.show_selected_figure()

    def show_selected_figure(self, event=None):
        name = self.det_figpick.get()
        path = os.path.join(RESULTS_DIR, name) if name else None
        if not path or not os.path.exists(path):
            return
        try:
            import matplotlib.image as mpimg
            self.det_fig.clear()
            ax = self.det_fig.add_subplot(111)
            img = mpimg.imread(path)
            ax.imshow(img)
            ax.axis("off")
            self.det_fig.tight_layout()
            self.det_canvas.draw_idle()
        except Exception as e:
            self.log(f"Không hiển thị được hình: {e!r}", "err")

    def open_figure_external(self):
        name = self.det_figpick.get()
        p = os.path.join(RESULTS_DIR, name) if name else None
        if p and os.path.exists(p):
            os.startfile(p)

    def _result_file(self, suffix):
        stem = os.path.splitext(os.path.basename(self.det_file.get().strip()))[0]
        return os.path.join(RESULTS_DIR, stem, suffix)

    def open_report(self):
        p = self._result_file("detect_report.txt")
        if os.path.exists(p):
            os.startfile(p)
        else:
            self.log(f"Chưa có báo cáo: {p}", "err")

    def open_last_result_dir(self):
        stem = os.path.splitext(os.path.basename(self.det_file.get().strip()))[0]
        d = os.path.join(RESULTS_DIR, stem)
        self.open_dir(d if os.path.isdir(d) else RESULTS_DIR)

    def open_metrics(self):
        p = self._result_file("detect_metrics.json")
        if os.path.exists(p):
            os.startfile(p)
        else:
            self.log(f"Chưa có metrics: {p}", "err")

    # ------------------------------------------------------------ TAB 3 actions
    def _tgt_date(self):
        s = self.tgt_date.get().strip()
        return s or None

    def tgt_transit(self):
        # ĐỌC WIDGET PHẢI Ở MAIN THREAD (Tkinter không thread-safe) —
        # nếu để lambda tự gọi .get() trong worker sẽ ném
        # "main thread is not in main loop".
        bw = float(self.tgt_bw.get())
        date_str = self._tgt_date()
        self.run_into(self.tgt_out,
                      lambda: psr_targets.print_transit(date_str, bw_mhz=bw))

    def tgt_daytime(self):
        date_str = self._tgt_date()
        self.run_into(self.tgt_out,
                      lambda: psr_targets.print_daytime(date_str))

    def tgt_snr(self):
        self.run_into(self.tgt_out,
                      lambda: psr_targets.print_pulsars(psr_targets.table_pulsars()))

    def tgt_derived(self):
        self.run_into(self.tgt_out, lambda: psr_targets.print_derived())

    def tgt_objects(self):
        self.run_into(self.tgt_out, lambda: psr_targets.print_objects())

    # ------------------------------------------------------------ TAB 4 actions
    def hw_detect(self):
        band = self.hw_band.get()
        goal = self.hw_goal.get()

        def job():
            import psr_hw
            c = psr_hw.detect_chain(band, goal=goal)
            txt = c.summary()
            self.post(lambda: (self.hw_out.configure(state="normal"),
                               self.hw_out.delete("1.0", "end"),
                               self.hw_out.insert("end", txt),
                               self.hw_out.configure(state="disabled")))
        self.run_bg(job)

    def hw_selfcheck(self):
        def job():
            import psr_hw
            errs = psr_hw.self_check()
            txt = "Tự kiểm tra công thức phần cứng: OK" if not errs \
                else "LỖI:\n" + "\n".join(errs)
            self.post(lambda: (self.hw_out.configure(state="normal"),
                               self.hw_out.insert("end", txt + "\n"),
                               self.hw_out.configure(state="disabled")))
        self.run_bg(job)

    # ------------------------------------------------------------ TAB 5 actions
    def run_selftest(self):
        self.chk_out.configure(state="normal")
        self.chk_out.delete("1.0", "end")
        self.chk_out.configure(state="disabled")

        def job():
            import selftest as st
            import contextlib as _ctx
            st.RESULT.clear()
            buf = []

            class W:
                def write(self, s):
                    if s and s.strip():
                        buf.append(str(s))
                def flush(self):
                    pass

            with _ctx.redirect_stdout(W()):
                st.test_physics()
                st.test_dedispersion()
                st.test_snr_calibration()
                st.test_sensitivity_formula()
                st.test_period_refine()
                st.test_subband_dm()
                st.test_targets()
                st.test_zero_dm_keeps_pulse()
                st.test_subband_dm_single()
                st.test_find_pulses_cluster()
                st.test_fil_roundtrip()
            ok = sum(st.RESULT)
            buf.append(f"\n==== {ok}/{len(st.RESULT)} test PASS ====")
            txt = "\n".join(buf)
            self.post(lambda: (self.chk_out.configure(state="normal"),
                               self.chk_out.insert("end", txt),
                               self.chk_out.see("end"),
                               self.chk_out.configure(state="disabled")))
        self.run_bg(job)

    def run_pipeline_quick(self):
        def job():
            import psr_pipeline
            psr_pipeline.run(quick=True)
        self.run_bg(job, on_done=self._refresh_figure_list)

    def run_stress(self):
        """Chạy toàn bộ corpus dữ liệu xấu (kể cả ca TIÊM vào nền RFI thật)."""
        def job():
            import stress_test
            stress_test.main()
        self.run_bg(job, on_done=self._refresh_figure_list)

    def run_recorder_selftest(self):
        def job():
            import record_unattended as ru
            ok = ru.selftest()
            self.log(f"Recorder selftest: {'PASS' if ok else 'FAIL'}",
                     "ok" if ok else "err")
        self.run_bg(job)


# ---------------------------------------------------------------- selfcheck EXE
def selfcheck() -> int:
    """Nghiệm thu bản ĐÓNG GÓI: import, đường dẫn, công thức, IQ, PSRFITS, xuất file."""
    import io
    import shutil
    import tempfile
    lines = [f"selfcheck {datetime.now():%Y-%m-%d %H:%M:%S}",
             f"frozen = {FROZEN}", f"APP_DIR = {APP_DIR}", f"DATA_DIR = {DATA_DIR}",
             f"RESULTS_DIR = {RESULTS_DIR}"]
    ok = True

    def chk(name, cond, detail=""):
        nonlocal ok
        ok = ok and bool(cond)
        lines.append(f"[{'PASS' if cond else 'FAIL'}] {name}"
                     + (f" — {detail}" if detail else ""))

    try:
        import psr_core, psr_fil, psr_sim, psr_sensitivity, psr_targets   # noqa
        import psr_hw, psr_swcomp, psr_plots, psr_detect, psr_pipeline    # noqa
        import psr_iq, psr_fits, record_unattended, selftest              # noqa
        chk("import toàn bộ module (kể cả psr_iq, psr_fits)", True)
    except Exception as e:
        chk("import toàn bộ module", False, repr(e))

    try:
        chk("psr_hw.self_check", not psr_hw.self_check())
    except Exception as e:
        chk("psr_hw.self_check", False, repr(e))

    ico = asset_path("icon.ico")
    chk("icon app tồn tại (assets/icon.ico)", bool(ico), ico or "THIẾU")

    tmp = tempfile.mkdtemp(prefix="psrself_")
    try:
        # --- IQ: SigMF ci16 → channelize → đúng tần số
        import numpy as np
        fs, fc, n = 2.4e6, 423e6, 48000
        t = np.arange(n) / fs
        rng = np.random.default_rng(0)
        iq = (rng.normal(0, 1, n) + 1j * rng.normal(0, 1, n)) * 3000
        iq += np.exp(2j * np.pi * 30e3 * t) * 9000
        stem = os.path.join(tmp, "iq")
        psr_iq.write_sigmf(stem, iq, fs, fc, "ci16_le")
        h, dyn = psr_iq.read_iq_as_dyn(stem + ".sigmf-data", nchan=128)
        f = h["freqs_mhz"]
        peak = f[int(np.argmax(dyn.mean(axis=1)))]
        chk("IQ SigMF → channelize đúng tần số", abs(peak - 423.03) < 0.1,
            f"đỉnh {peak:.3f} MHz")
    except Exception as e:
        chk("IQ SigMF → channelize", False, repr(e))

    try:
        import numpy as np
        d = np.random.default_rng(1).normal(100, 10, (64, 3000)).astype(np.float32)
        p = os.path.join(tmp, "rt.fits")
        psr_fits.write_psrfits(p, d, tsamp_s=2.5e-4, f_center_mhz=1420.0,
                               bw_mhz=32.0)
        hh, d2 = psr_fits.read_psrfits(p, strict=True)
        err = float(np.max(np.abs(d2 - d)))
        chk("PSRFITS ghi→đọc round-trip", d2.shape == d.shape and err < 1.0,
            f"sai số {err:.2f} đơn vị ADC")
    except Exception as e:
        chk("PSRFITS ghi→đọc round-trip", False, repr(e))

    try:
        # --- xuất file: chạy detect trên .fil nhỏ, kiểm tra 4 tệp ra
        import numpy as np
        d = np.random.default_rng(2).normal(100, 10, (64, 4000)).astype(np.float32)
        for k in range(6):
            d[:, 300 + k * 600:303 + k * 600] += 45
        fil = os.path.join(tmp, "acc.fil")
        psr_fil.write_fil(fil, d, dict(source_name="SELF", nchans=64, nifs=1,
                                       nbeams=1, telescope_id=6, machine_id=0,
                                       data_type=1, tsamp=2.5e-4, tstart=60000.0,
                                       fch1=1420.0, foff=-0.5, nbits=8))
        old = psr_detect.RESULTS
        psr_detect.RESULTS = tmp
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                psr_detect.detect(fil)
        finally:
            psr_detect.RESULTS = old
        outd = os.path.join(tmp, "acc")
        need = ["fig1_overview.png", "fig2_detection.png",
                "detect_metrics.json", "detect_report.txt"]
        got = [f for f in need if os.path.exists(os.path.join(outd, f))]
        chk("phát hiện + xuất đủ 4 tệp", len(got) == 4, f"{len(got)}/4")
        import json as _json
        with open(os.path.join(outd, "detect_metrics.json"), encoding="utf-8") as fh:
            js = _json.load(fh)
        chk("metrics JSON hợp lệ", all(k in js for k in ("stage", "output_checks")),
            f"{len(js)} khoá")
    except Exception as e:
        chk("phát hiện + xuất đủ 4 tệp", False, repr(e))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    try:
        import selftest as st
        st.RESULT.clear()
        with contextlib.redirect_stdout(io.StringIO()):
            st.test_physics()
            st.test_fil_roundtrip()
            st.test_iq_channelize()
        chk("selftest rút gọn (vật lý + fil + IQ)", sum(st.RESULT) == len(st.RESULT),
            f"{sum(st.RESULT)}/{len(st.RESULT)}")
    except Exception as e:
        chk("selftest rút gọn", False, repr(e))

    lines.append("RESULT: " + ("PASS" if ok else "FAIL"))
    txt = "\n".join(lines)
    for dest in (os.path.join(APP_DIR, "selfcheck_report.txt"),
                 os.path.join(ROOT_DIR, "selfcheck_report.txt")):
        try:
            with open(dest, "w", encoding="utf-8") as fh:
                fh.write(txt + "\n")
        except Exception:
            pass
    return 0 if ok else 1


def main():
    if "--selfcheck" in sys.argv:
        sys.exit(selfcheck())
    root = tk.Tk()
    try:
        root.iconbitmap(default="")          # tránh lỗi icon khi đóng gói
    except Exception:
        pass
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()