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


def _win32_set_icons(root, ico: str) -> str:
    """Gắn icon TRỰC TIẾP qua Win32: WM_SETICON + icon của class.

    Vì sao cần: Tk trên Windows có thể tạo lại HWND khi cửa sổ hiện ra, làm mất
    icon đã đặt bằng wm iconbitmap → taskbar hiện icon mặc định của Tk (lông vũ).
    Đặt cả icon CLASS thì cửa sổ tạo lại vẫn thừa hưởng.

    LƯU Ý: BẮT BUỘC khai báo argtypes — nếu không, handle 64-bit bị cắt còn
    32-bit và WM_SETICON nhận handle rác (đã gặp: icon không hiện dù không lỗi).
    """
    try:
        import ctypes
        import ctypes.wintypes as wt
        u = ctypes.windll.user32
        u.LoadImageW.argtypes = [wt.HINSTANCE, wt.LPCWSTR, wt.UINT,
                                 ctypes.c_int, ctypes.c_int, wt.UINT]
        u.LoadImageW.restype = wt.HANDLE
        u.SendMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
        u.SendMessageW.restype = wt.LPARAM
        u.SetClassLongPtrW.argtypes = [wt.HWND, ctypes.c_int, ctypes.c_void_p]
        u.SetClassLongPtrW.restype = ctypes.c_void_p
        u.GetParent.argtypes = [wt.HWND]
        u.GetParent.restype = wt.HWND
        IMAGE_ICON, LR_LOADFROMFILE = 1, 0x10
        big = u.LoadImageW(None, ico, IMAGE_ICON, 0, 0, LR_LOADFROMFILE)
        small = u.LoadImageW(None, ico, IMAGE_ICON, 16, 16, LR_LOADFROMFILE)
        if not big and not small:
            return "LoadImage lỗi"
        root.update_idletasks()
        h = int(root.winfo_id())
        targets = [h]
        for _ in range(4):                    # HWND thật nằm ở cấp cha
            p = u.GetParent(targets[-1])
            if not p:
                break
            targets.append(p)
        for hw in targets:
            if big:
                u.SendMessageW(hw, 0x0080, 1, big)     # WM_SETICON, ICON_BIG
                u.SetClassLongPtrW(hw, -14, big)       # GCLP_HICON
            if small:
                u.SendMessageW(hw, 0x0080, 0, small)   # WM_SETICON, ICON_SMALL
                u.SetClassLongPtrW(hw, -34, small)     # GCLP_HICONSM
        return f"win32=ok ({len(targets)} hwnd)"
    except Exception as e:
        return f"win32 lỗi: {e!r}"


def _icon_is_set(root) -> bool:
    """True nếu cửa sổ THẬT SỰ có icon riêng (WM_GETICON khác 0).

    Đây là kiểm tra bắt đúng lỗi "taskbar hiện icon mặc định của Tk" — lỗi này
    từng xảy ra dù mọi lệnh gọi không hề báo lỗi.
    """
    try:
        import ctypes
        import ctypes.wintypes as wt
        u = ctypes.windll.user32
        u.SendMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
        u.SendMessageW.restype = wt.LPARAM
        h = int(root.winfo_id())
        return bool(u.SendMessageW(h, 0x007F, 1, 0))   # WM_GETICON, ICON_BIG
    except Exception:
        return False


def apply_icon(root) -> str:
    """Gắn icon cho cửa sổ + title bar + taskbar Windows."""
    info = []
    ico = asset_path("icon.ico")
    png = asset_path("icon.png")
    if ico:
        try:
            root.iconbitmap(default=ico)
            info.append("iconbitmap=ok")
        except Exception as e:
            info.append(f"iconbitmap lỗi: {e!r}")
    if png:
        try:
            from tkinter import PhotoImage
            img = PhotoImage(file=png)
            root.iconphoto(True, img)
            root._icon_ref = img          # giữ tham chiếu, nếu không sẽ mất
            info.append("iconphoto=ok")
        except Exception as e:
            info.append(f"iconphoto lỗi: {e!r}")
    if ico:
        info.append(_win32_set_icons(root, ico))
        # gắn lại sau khi cửa sổ hiện ra (Tk có thể tạo lại HWND lúc map)
        try:
            root.after(400, lambda: _win32_set_icons(root, ico))
            root.bind("<Map>", lambda _e: _win32_set_icons(root, ico))
        except Exception:
            pass
    return "; ".join(info) if info else "không có icon"


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


# ép module dùng đúng thư mục data/results (không phụ thuộc nơi khởi chạy)
import psr_detect            # noqa: E402
import record_unattended     # noqa: E402
import psr_hw                # noqa: E402
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


# Ba chế độ nguồn dữ liệu — hiển thị cho người dùng (giá trị thật là khoá)
SOURCE_MODES = {
    "auto": "Tự động (ưu tiên SDR thật — mặc định)",
    "mock": "Bắt buộc MÔ PHỎNG (chạy thử pipeline, không cần/không đụng SDR)",
    "real": "Bắt buộc SDR THẬT (mất kết nối → báo lỗi, không giả lập)",
}


class TargetDialog(tk.Toplevel):
    """Thêm / sửa / xoá MỤC TIÊU TỰ THÊM (không cần sửa code).

    Người dùng nhập: tên, RA, Dec (giờ-phút-giây hoặc độ), P, DM, flux, W50.
    Chỉ tên + RA + Dec là bắt buộc; P/DM/flux dùng cho dự đoán SNR và kiểm chứng
    nên có thể bỏ trống. Lưu vào targets_user.json cạnh ứng dụng.
    """

    FIELDS = (
        ("name", "Tên mục tiêu", "vd: PSR J1234+56, Cas A, Mục tiêu 1", 26),
        ("ra", "RA", "HH:MM:SS (giờ) hoặc độ, vd 12:34:56 / 188.733", 26),
        ("dec", "Dec", "±DD:MM:SS hoặc độ, vd -05:12:34 / -5.209", 26),
        ("P", "Chu kỳ P (s)", "bỏ trống nếu không biết — vd 0.253065", 26),
        ("dm", "DM (pc cm⁻³)", "bỏ trống nếu không biết — vd 2.97", 26),
        ("s408", "Flux 408 MHz (mJy)", "bỏ trống nếu không biết", 26),
        ("s1400", "Flux 1400 MHz (mJy)", "bỏ trống nếu không biết", 26),
        ("w408", "W50 408 MHz (ms)", "bỏ trống → dùng 25 ms để dự đoán", 26),
        ("w1400", "W50 1400 MHz (ms)", "bỏ trống → dùng 6 ms để dự đoán", 26),
        ("note", "Ghi chú", "nguồn gốc, mục đích quan sát…", 46),
    )

    def __init__(self, master, app: "App", edit_name: str | None = None):
        super().__init__(master)
        self.app = app
        self.title("Mục tiêu — thêm/sửa (lưu vào targets_user.json)")
        self.transient(master)
        self.resizable(False, False)
        self.vars = {}
        f = ttk.Frame(self)
        f.pack(fill="both", padx=10, pady=10)
        tgt = psr_targets.find_target(edit_name) if edit_name else None
        for r, (key, label, hint, w) in enumerate(self.FIELDS):
            ttk.Label(f, text=label + ":").grid(row=r, column=0, sticky="w",
                                                 padx=4, pady=3)
            var = tk.StringVar()
            ent = ttk.Entry(f, textvariable=var, width=w)
            ent.grid(row=r, column=1, sticky="we", padx=4, pady=3)
            ttk.Label(f, text=hint, foreground="#5f5f5f").grid(
                row=r, column=2, sticky="w", padx=4)
            self.vars[key] = var
            if tgt and tgt.get(key) not in (None, ""):
                v = tgt[key]
                if key in ("ra", "dec"):
                    var.set(f"{float(v):.5f}" if isinstance(v, (int, float)) else str(v))
                else:
                    var.set(str(v))
        self.msg = ttk.Label(f, text="", foreground="#c00", wraplength=520,
                             justify="left")
        self.msg.grid(row=len(self.FIELDS), column=0, columnspan=3, sticky="w",
                      padx=4, pady=(6, 0))
        bf = ttk.Frame(f)
        bf.grid(row=len(self.FIELDS) + 1, column=0, columnspan=3, sticky="we",
                pady=(10, 0))
        ttk.Button(bf, text="Lưu", command=self._save).pack(side="left", padx=4)
        if tgt and tgt.get("custom"):
            ttk.Button(bf, text="Xoá mục tiêu", command=self._delete).pack(
                side="left", padx=4)
        ttk.Button(bf, text="Đóng", command=self.destroy).pack(side="right", padx=4)
        ttk.Label(f, foreground="#5f5f5f", wraplength=560, justify="left", text=(
            "· RA có dấu ':' được hiểu là GIỜ-PHÚT-GIÂY; chỉ nhập số thì là ĐỘ."
        )).grid(row=len(self.FIELDS) + 2, column=0, columnspan=3, sticky="w",
                padx=4, pady=(8, 0))
        self.grab_set()

    def _collect(self) -> dict:
        d = {}
        for key, var in self.vars.items():
            txt = var.get().strip()
            if not txt:
                continue
            if key == "name" or key == "note":
                d[key] = txt
            elif key == "ra":
                d["ra"] = psr_targets.parse_ra(txt)
            elif key == "dec":
                d["dec"] = psr_targets.parse_dec(txt)
            else:
                d[key] = float(txt.replace(",", "."))
        return d

    def _save(self) -> None:
        try:
            d = self._collect()
        except ValueError as exc:
            self.msg.configure(text=f"Không đọc được số: {exc}")
            return
        problems = psr_targets.validate_target(d)
        if problems:
            self.msg.configure(text="Sửa giúp: " + "; ".join(problems))
            return
        try:
            item = psr_targets.upsert_target(d)
        except Exception as exc:
            self.msg.configure(text=f"Không lưu được: {exc}")
            return
        self.app.log(f"Đã lưu mục tiêu '{item['name']}' "
                     f"(RA {item['ra']:.4f}°, Dec {item['dec']:+.4f}°)", "ok")
        self.app.refresh_target_list(select=item["name"])
        self.destroy()

    def _delete(self) -> None:
        name = self.vars["name"].get().strip()
        if not messagebox.askyesno("Xoá mục tiêu", f"Xoá '{name}' khỏi danh mục?"):
            return
        ok = psr_targets.delete_target(name)
        self.app.log((f"Đã xoá mục tiêu '{name}'" if ok
                      else f"'{name}' không có trong danh mục tự thêm"),
                     "ok" if ok else "err")
        self.app.refresh_target_list()
        self.destroy()


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
        self.rec_target = ttk.Combobox(f, values=[], width=18)
        # CHO PHÉP GÕ TAY: quan sát nguồn ngoài danh mục, không bị khoá cứng
        self.rec_target.configure(state="normal")
        self.rec_target.set("B0950+08")
        self.rec_target.grid(row=0, column=1, padx=4, pady=4, sticky="we")
        ttk.Button(f, text="＋ Mục tiêu…", width=13,
                   command=self.manage_targets).grid(row=0, column=2, padx=(0, 6))

        ttk.Label(f, text="Băng (MHz):").grid(row=0, column=3, sticky="w", padx=4)
        self.rec_band = ttk.Combobox(f, values=["423", "1420"], width=6)
        self.rec_band.set("423")
        self.rec_band.grid(row=0, column=4, padx=4)

        ttk.Label(f, text="Thời lượng (giờ):").grid(row=0, column=5, sticky="w", padx=4)
        self.rec_hours = ttk.Spinbox(f, from_=0.5, to=8.0, increment=0.5, width=6)
        self.rec_hours.set(4.5)
        self.rec_hours.grid(row=0, column=6, padx=4)

        ttk.Label(f, text="Kênh:").grid(row=1, column=0, sticky="w", padx=4)
        self.rec_nchan = ttk.Spinbox(f, from_=16, to=512, increment=16, width=6)
        self.rec_nchan.set(64)
        self.rec_nchan.grid(row=1, column=1, padx=4, sticky="w")

        ttk.Label(f, text="tsamp (µs):").grid(row=1, column=3, sticky="w", padx=4)
        self.rec_tsamp = ttk.Spinbox(f, from_=64, to=2000, increment=64, width=6)
        self.rec_tsamp.set(256)
        self.rec_tsamp.grid(row=1, column=4, padx=4, sticky="w")

        ttk.Label(f, text="Nguồn dữ liệu:").grid(row=2, column=0, sticky="w",
                                                 padx=4, pady=(6, 4))
        self.rec_source = ttk.Combobox(
            f, values=list(SOURCE_MODES.values()), state="readonly", width=44)
        self.rec_source.set(SOURCE_MODES["auto"])
        self.rec_source.grid(row=2, column=1, columnspan=3, sticky="we", padx=4,
                             pady=(6, 4))
        self.rec_source.bind("<<ComboboxSelected>>", lambda _e: self.refresh_hw_status())

        # nhãn trạng thái phần cứng ngay cạnh vùng ghi + nút Làm mới
        self.rec_hw_label = ttk.Label(f, text="… đang dò thiết bị", width=46)
        self.rec_hw_label.grid(row=2, column=4, columnspan=2, sticky="w", padx=4)
        ttk.Button(f, text="Làm mới", width=9,
                   command=self.refresh_hw_status).grid(row=2, column=6, sticky="w")

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

        self.refresh_target_list(select="B0950+08")
        self.rec_source.set(SOURCE_MODES["auto"])
        self.root.after_idle(lambda: self.refresh_hw_status())

        info = ttk.LabelFrame(self.tab_rec, text="Cách dùng")
        info.pack(fill="both", expand=True, padx=8, pady=8)
        ttk.Label(info, justify="left", wraplength=1000, text=(
            "· Trước khi treo chảo: python psr_targets.py --transit (hoặc tab 3) để biết giờ transit.\n"
            "· Nguồn dữ liệu mặc định TỰ ĐỘNG: có SDR là thu thật, không có thì mô phỏng\n"
            "  (nhãn 🟡 cảnh báo ngay cạnh). Treo máy qua đêm nên chọn BẮT BUỘC SDR THẬT.\n"
            "· Sau khi cắm/rút dây: bấm Làm mới cạnh nhãn trạng thái để dò lại thiết bị.\n"
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
                         ("Bảng SNR (mọi mục tiêu) × 5 cấu hình", self.tgt_snr),
                         ("Đại lượng suy ra (B, tuổi, Ė)", self.tgt_derived),
                         ("Nguồn continuum khác", self.tgt_objects),
                         ("＋ Quản lý mục tiêu…", self.manage_targets)):
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
    # ---- nguồn dữ liệu: tự dò SDR, hiện trạng thái, cho ép chế độ
    def _source_key(self) -> str:
        """Khoá chế độ đang chọn ('auto' | 'mock' | 'real')."""
        txt = self.rec_source.get()
        for k, v in SOURCE_MODES.items():
            if v == txt:
                return k
        return "auto"

    def refresh_hw_status(self) -> None:
        """Dò SDR và cập nhật nhãn trạng thái (🟢 thật / 🟡 mô phỏng)."""
        mode = self._source_key()
        probe = psr_hw.probe_sdr()
        if mode == "mock":
            text, col = "🟡 Bắt buộc MÔ PHỎNG — dữ liệu không phải thu thật", "#b36b00"
        elif probe["found"]:
            tun = f" ({probe['tuner']})" if probe.get("tuner") else ""
            text = f"🟢 {probe['name']}{tun}: đã kết nối"
            col = "#1a7f37"
        elif mode == "real":
            text = f"🔴 KHÔNG có SDR — chế độ bắt buộc thật sẽ BÁO LỖI"
            col = "#c62828"
        else:
            text = "🟡 Tự động → MÔ PHỎNG (không thấy SDR)"
            col = "#b36b00"
        try:
            self.rec_hw_label.configure(text=text, foreground=col)
        except Exception:
            pass
        self._last_probe = probe
        return probe

    # ---- mục tiêu: danh sách linh hoạt (thêm/sửa/xoá, gõ tay tên bất kỳ)
    def refresh_target_list(self, select: str | None = None,
                            keep_current: bool = True) -> None:
        """Nạp lại danh sách mục tiêu (có sẵn + tự thêm) vào combobox."""
        items = psr_targets.all_pulsars()
        names = [t["name"] for t in items]
        cur = select or self.rec_target.get()
        if keep_current and cur and str(cur).strip().lower() not in {
                n.lower() for n in names}:
            names.append(cur)          # giữ tên người dùng đang gõ
        self.rec_target.configure(values=names)
        if select:
            self.rec_target.set(select)
        elif not keep_current:
            self.rec_target.set(names[0] if names else "")
        self._target_items = items

    def manage_targets(self) -> None:
        """Mở hộp thoại thêm/sửa mục tiêu (mặc định là mục tiêu đang chọn)."""
        name = self.rec_target.get().strip()
        tgt = psr_targets.find_target(name)
        TargetDialog(self.root, self,
                     edit_name=name if (tgt and tgt.get("custom")) else None)

    def resolve_target(self, name: str) -> dict | None:
        """Tra mục tiêu; nếu chưa có thì hỏi người dùng khai báo ngay.

        Trả về dict mục tiêu, hoặc None nếu người dùng chọn "ghi không cần toạ độ"
        (vẫn ghi được — chỉ không dự đoán được transit/SNR).
        """
        name = (name or "").strip()
        if not name:
            messagebox.showerror("Thiếu mục tiêu", "Hãy nhập tên mục tiêu.")
            return None
        tgt = psr_targets.find_target(name)
        if tgt:
            return tgt
        ans = messagebox.askyesnocancel(
            "Mục tiêu chưa có trong danh mục",
            f"'{name}' không có trong danh mục, nên không tính được giờ transit / "
            f"SNR dự đoán.\n\nCó = khai báo ngay (RA, Dec, P, DM…)\n"
            f"Không = vẫn ghi dữ liệu, chỉ không có dự đoán\n"
            f"Cancel = quay lại")
        if ans is None:
            return None
        if ans:
            TargetDialog(self.root, self, edit_name=name)
            return psr_targets.find_target(name)   # có thể None nếu chưa lưu
        return dict(name=name, custom=True, ra=None, dec=None)

    def start_recording(self):
        target_name = self.rec_target.get().strip()
        tgt = self.resolve_target(target_name)
        if tgt is None:
            return
        try:
            hours = float(self.rec_hours.get())
            nchan = int(self.rec_nchan.get())
            tsamp = float(self.rec_tsamp.get())
        except ValueError:
            messagebox.showerror("Lỗi", "Giờ/kênh/tsamp phải là số")
            return
        source = self._source_key()
        probe = self.refresh_hw_status()
        if source == "real" and not probe["found"]:
            messagebox.showerror(
                "Không có SDR",
                "\n".join([
                    "Đang chọn 'Bắt buộc SDR THẬT' nhưng không tìm thấy thiết bị:",
                    str(probe.get("error") or "không rõ lý do"),
                    "",
                    "Cắm lại thiết bị rồi bấm Làm mới, hoặc đổi sang 'Tự động'.",
                ]))
            return
        if source == "auto" and not probe["found"]:
            if not messagebox.askokcancel(
                    "Không thấy SDR — sẽ ghi MÔ PHỎNG",
                    "\n".join([
                        "Không tìm thấy RTL-SDR:",
                        "   " + str(probe.get("error") or "không rõ lý do"),
                        "",
                        "OK = ghi dữ liệu MÔ PHỎNG (để kiểm chứng chuỗi)",
                        "Cancel = dừng lại để cắm thiết bị",
                    ])):
                return
        target = tgt["name"]
        band = self.rec_band.get()
        self.log(f"Bắt đầu ghi: {target} @ {band} MHz, {hours} h, "
                 f"{nchan} kênh × {tsamp:.0f} µs, nguồn={source}")
        if source != "mock":
            self.log("   " + ("SDR: đã thấy thiết bị" if probe["found"]
                              else "SDR: KHÔNG thấy → mô phỏng"),
                     "ok" if probe["found"] else "err")
        if tgt.get("ra") is not None and tgt.get("dec") is not None:
            try:
                self.log(f"   mục tiêu: RA {tgt['ra']:.4f}°, Dec {tgt['dec']:+.4f}°"
                         + ("  [tự thêm]" if tgt.get("custom") else ""))
            except Exception:
                pass

        def job():
            record_unattended.run_session(
                target=target, hours=hours, band=band, source=source,
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
VERSION = "1.2.0"


def selfcheck() -> int:
    """Nghiệm thu bản ĐÓNG GÓI: import, đường dẫn, công thức, IQ, PSRFITS, xuất file."""
    import io
    import shutil
    import tempfile
    lines = [f"selfcheck {datetime.now():%Y-%m-%d %H:%M:%S} — v{VERSION}",
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

    # ---- ĐĨA: danh mục mục tiêu + thư mục ghi (điểm hay hỏng khi đóng gói EXE)
    try:
        import os as _os
        _p = psr_targets.user_targets_path()
        _n0 = len(psr_targets.all_pulsars())
        psr_targets.upsert_target(dict(name="ZZ_SELFCHECK", ra=10.0, dec=-10.0,
                                       P=0.5, dm=10.0))
        _ok_write = _os.path.exists(_p) and bool(psr_targets.find_target("ZZ_SELFCHECK"))
        _ok_read = len(psr_targets.all_pulsars()) == _n0 + 1
        psr_targets.delete_target("ZZ_SELFCHECK")
        _ok_del = len(psr_targets.all_pulsars()) == _n0
        chk("danh mục mục tiêu ghi/đọc/xoá được cạnh app", _ok_write and _ok_read and _ok_del,
            _p)
    except Exception as e:
        chk("danh mục mục tiêu ghi/đọc/xoá được cạnh app", False, repr(e))

    try:
        import os as _os
        for _d in (DATA_DIR, RESULTS_DIR):
            _os.makedirs(_d, exist_ok=True)
        _w = all(_os.access(_d, _os.W_OK) for _d in (DATA_DIR, RESULTS_DIR))
        chk("thư mục data/ và results/ tồn tại và ghi được", _w, APP_DIR)
    except Exception as e:
        chk("thư mục data/ và results/ tồn tại và ghi được", False, repr(e))
    try:
        import tkinter as _tk
        _r = _tk.Tk()
        _r.withdraw()
        _info = apply_icon(_r)
        _r.update()
        _ok_icon = _icon_is_set(_r)
        _r.destroy()
        chk("icon gắn được vào cửa sổ (WM_GETICON)", _ok_icon, _info)
    except Exception as e:
        chk("icon gắn được vào cửa sổ (WM_GETICON)", False, repr(e))

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
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()