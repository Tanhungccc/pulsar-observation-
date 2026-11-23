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
DATA_DIR = os.path.join(ROOT_DIR, "data")        # sẽ được psr_paths xác nhận
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
import psr_paths             # noqa: E402
import psr_i18n as L         # noqa: E402
import psr_theme as theme    # noqa: E402  (bộ quy chuẩn "Observatory Workspace")

DATA_DIR = psr_paths.data_dir()          # một nơi duy nhất quyết định đường dẫn
RESULTS_DIR = psr_paths.results_dir()
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
        self.title(L.t("Mục tiêu — thêm/sửa (lưu vào targets_user.json)"))
        self.transient(master)
        self.resizable(False, False)
        try:                                     # nền theo chủ đề đang dùng
            pal = theme.P()
            self.configure(background=pal["bg"])
        except Exception:                        # noqa: BLE001
            pass
        self.vars = {}
        f = ttk.Frame(self)
        f.pack(fill="both", padx=theme.sp(12), pady=theme.sp(12))
        ttk.Label(f, text=L.t("MỤC TIÊU"), style="H2.TLabel").grid(
            row=0, column=0, columnspan=3, sticky="w", padx=theme.sp(4),
            pady=(0, theme.sp(6)))
        tgt = psr_targets.find_target(edit_name) if edit_name else None
        for r, (key, label, hint, w) in enumerate(self.FIELDS, start=1):
            ttk.Label(f, text=label + ":", style="CardMuted.TLabel").grid(
                row=r, column=0, sticky="w", padx=theme.sp(4), pady=theme.sp(2))
            var = tk.StringVar()
            ent = ttk.Entry(f, textvariable=var, width=w)
            ent.grid(row=r, column=1, sticky="we", padx=theme.sp(4),
                     pady=theme.sp(2))
            ttk.Label(f, text=hint, style="CardMuted.TLabel").grid(
                row=r, column=2, sticky="w", padx=theme.sp(4))
            self.vars[key] = var
            if tgt and tgt.get(key) not in (None, ""):
                v = tgt[key]
                if key in ("ra", "dec"):
                    var.set(f"{float(v):.5f}" if isinstance(v, (int, float)) else str(v))
                else:
                    var.set(str(v))
        self.msg = ttk.Label(f, text="", style="Err.TLabel", wraplength=520,
                             justify="left")
        self.msg.grid(row=len(self.FIELDS) + 1, column=0, columnspan=3,
                      sticky="w", padx=theme.sp(4), pady=(theme.sp(6), 0))
        bf = ttk.Frame(f)
        bf.grid(row=len(self.FIELDS) + 2, column=0, columnspan=3, sticky="we",
                pady=(theme.sp(10), 0))
        ttk.Button(bf, text=L.t("Lưu"), style="Primary.TButton",
                   command=self._save).pack(side="left", padx=theme.sp(4))
        if tgt and tgt.get("custom"):
            ttk.Button(bf, text=L.t(L.t("Xoá mục tiêu")), style="Stop.TButton",
                       command=self._delete).pack(side="left", padx=theme.sp(4))
        ttk.Button(bf, text=L.t("Đóng"), style="Ghost.TButton",
                   command=self.destroy).pack(side="right", padx=theme.sp(4))
        ttk.Label(f, style="CardMuted.TLabel", wraplength=560, justify="left", text=(
            L.t("· RA có dấu ':' được hiểu là GIỜ-PHÚT-GIÂY; chỉ nhập số thì là ĐỘ.")
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
            self.msg.configure(text=L.t("Sửa giúp: ") + "; ".join(problems))
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
        if not messagebox.askyesno(L.t("Xoá mục tiêu"), f"Xoá '{name}' khỏi danh mục?"):
            return
        ok = psr_targets.delete_target(name)
        self.app.log((f"Đã xoá mục tiêu '{name}'" if ok
                      else f"'{name}' không có trong danh mục tự thêm"),
                     "ok" if ok else "err")
        self.app.refresh_target_list()
        self.destroy()


class SegmentedChoice(ttk.Frame):
    """Bộ chọn 3 trạng thái dạng NÚT PHÂN ĐOẠN (không phải dropdown).

    Vì sao: 'Chưa xác định' là trạng thái THẬT (chưa dò thiết bị), nếu để trong
    dropdown thì người vận hành dễ chọn nhầm và tưởng đã kết nối. Ba nút nằm
    cạnh nhau, mỗi nút có ký hiệu ● (đang chọn) / ○ (chưa chọn) nên đọc được cả
    khi không phân biệt màu.

    Giữ nguyên API của ttk.Combobox mà app và bộ test đang dùng:
      .set(v) · .get() · .cget("values")
    """

    def __init__(self, master, values, on_change=None, marker=("●", "○"),
                 labels=None):
        super().__init__(master)
        self._values = list(values)
        # nhãn NGẮN hiển thị trên nút; giá trị dài vẫn là thứ .get() trả về
        self._labels = list(labels) if labels else list(self._values)
        self._on_change = on_change
        self._marker = marker
        self._var = tk.StringVar(value=self._values[0] if self._values else "")
        self._btns = []
        for i, v in enumerate(self._values):
            b = ttk.Button(self, style="Ghost.TButton",
                           text=self._labels[i] if i < len(self._labels) else v,
                           command=lambda k=i: self._choose(k))
            b.pack(side="left", padx=(0, theme.sp(4)))
            self._btns.append(b)
        self._render()

    def _render(self) -> None:
        cur = self._var.get()
        for i, (v, b) in enumerate(zip(self._values, self._btns)):
            on = (v == cur)
            lab = self._labels[i] if i < len(self._labels) else v
            b.configure(text=(self._marker[0] + " " if on
                              else self._marker[1] + " ") + lab,
                        style="Primary.TButton" if on else "Ghost.TButton")

    def _choose(self, idx: int) -> None:
        self.set(self._values[idx], notify=True)

    # ---- API tương thích Combobox
    def set(self, value, notify: bool = True):
        if value not in self._values:
            return
        self._var.set(value)
        self._render()
        if notify and self._on_change is not None:
            self._on_change(value)

    def get(self) -> str:
        return self._var.get()

    def cget(self, key):
        if key in ("values", "-values"):
            return tuple(self._values)
        return super().cget(key)

    def configure(self, **kw):
        if "values" in kw:
            self._values = list(kw.pop("values"))
        return super().configure(**kw)


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(L.t("Pulsar Observation — POAM RTP-3.7 (TP.HCM)"))
        self.icon_info = apply_icon(self.root)
        # Kích thước cửa sổ LẤY THEO MÀN HÌNH THẬT (đọc sau khi đã DPI-aware):
        # cửa sổ cố định 1240×710 trông nhỏ trên màn hình đang để 125–150 %.
        # Lấy ~94 % bề ngang / ~92 % chiều cao khả dụng, chặn trên để không
        # choáng, và căn giữa. Không phóng font giả — chỉ dùng đúng số pixel.
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        w = max(1100, min(int(sw * 0.94), 1680))
        h = max(680, min(int(sh * 0.92), 1040))
        x = max(0, (sw - w) // 2)
        y = max(0, (sh - h) // 3)
        self.root.geometry(f"{w}x{h}+{x}+{y}")
        self.root.minsize(min(1100, w), min(680, h))
        self._win_size = (w, h)

        self.q: queue.Queue = queue.Queue()      # chuỗi log từ thread phụ
        self.cbq: queue.Queue = queue.Queue()    # callable cần chạy ở MAIN thread
        self.writer = QueueWriter(self.q)
        self.busy = False
        self.stop_event = threading.Event()
        self.worker: threading.Thread | None = None

        self._build_style()
        self._build_layout()
        self._poll_queue()
        # Huỷ after(120ms) còn treo khi cửa sổ bị destroy — nếu không Tcl báo
        # 'invalid command name "..._poll_queue"' và có thể làm chết tiến trình
        # (đã gặp: gui_verify mất sạch output vì lỗi này lúc đóng cửa sổ).
        self.root.bind("<Destroy>", self._on_destroy, add="+")
        self.log(L.t("Sẵn sàng. Chọn tab để bắt đầu."))
        self.log(f"Thư mục dữ liệu: {DATA_DIR}")
        self.log(f"Thư mục kết quả: {RESULTS_DIR}")

    # ------------------------------------------------------------ giao diện
    def _build_style(self):
        """Áp bộ quy chuẩn giao diện (psr_theme): màu, kiểu chữ, ttk style."""
        self.ui = theme.apply_styles(self.root)
        self.pal = self.ui["palette"]
        self.fnt = self.ui["fonts"]
        try:                                     # nền cửa sổ + vùng tab
            self.root.configure(background=self.pal["bg"])
        except tk.TclError:
            pass

    def _build_layout(self):
        self._build_header()          # thanh tiêu đề: tên trạm + Sáng/Tối + VI/EN

        # ---- NHẬT KÝ CHUNG: đóng gói TRƯỚC với side="bottom" để nó luôn nằm
        # trong khung nhìn; notebook nhận phần cao còn lại (trước đây pack sau
        # nên khi nội dung tab dài, nhật ký bị đẩy ra ngoài màn hình).
        self._build_shared_log()

        self.nb = ttk.Notebook(self.root)
        self.nb.pack(side="top", fill="both", expand=True, padx=6, pady=(6, 4))

        # PHƯƠNG ÁN B: 3 tab — Kế hoạch & Ghi / Phát hiện / Cài đặt & Công cụ
        self.tab_plan = ttk.Frame(self.nb)
        self.tab_det = ttk.Frame(self.nb)
        self.tab_set = ttk.Frame(self.nb)
        self.nb.add(self.tab_plan, text=L.t("  1 · KẾ HOẠCH & GHI  "))
        self.nb.add(self.tab_det, text=L.t("  2 · PHÁT HIỆN  "))
        self.nb.add(self.tab_set, text=L.t("  3 · CÀI ĐẶT & CÔNG CỤ  "))
        # giữ tên cũ để code/test cũ không vỡ
        self.tab_rec = self.tab_plan
        self.tab_tgt = self.tab_set
        self.tab_hw = self.tab_set
        self.tab_chk = self.tab_set

        self._build_recorder_tab()      # tab 1: bảng kế hoạch + phiên ghi
        self._build_detect_tab()        # tab 2: phát hiện + guard
        self._build_settings_tab()      # tab 3: hồ sơ, danh mục, nơi lưu, công cụ

    def _build_header(self) -> None:
        """Thanh tiêu đề (nền đậm, cạnh vuông): tên trạm · kính · băng + hai nút
        phụ (Sáng/Tối, VI/EN). Không đặt chip trạng thái ở đây để khỏi trùng với
        chip trạng thái trong từng màn hình.
        """
        try:
            import psr_site as _site
            prof = _site.active_profile()
            meta = (f"{prof.site.name} · {prof.telescope.name} · "
                    f"{prof.telescope.diameter_m} m")
        except Exception:                        # noqa: BLE001
            meta = ""
        self.header = tk.Frame(self.root, background=self.pal["header"],
                               highlightthickness=0, bd=0)
        self.header.pack(side="top", fill="x")
        inner = ttk.Frame(self.header, style="Header.TFrame")
        inner.pack(fill="x", padx=theme.sp(10), pady=theme.sp(6))
        ttk.Label(inner, text="PULSAR OBSERVATION",
                  style="HeaderBrand.TLabel").pack(side="left")
        ttk.Label(inner, text="   " + meta,
                  style="HeaderMeta.TLabel").pack(side="left", padx=(theme.sp(6), 0))

        _dark = theme.mode() == "dark"
        self.btn_theme = ttk.Button(
            inner, text=L.t("Tối") if _dark else L.t("Sáng"),
            style="Header.TButton", width=9, command=self._toggle_theme)
        self.btn_theme.pack(side="right")
        self.btn_lang = ttk.Button(inner, text="VI / EN", style="Header.TButton",
                                   width=8, command=self._toggle_language)
        self.btn_lang.pack(side="right", padx=(0, theme.sp(6)))

    def _toggle_theme(self) -> None:
        """Đổi Sáng/Tối: ghi settings.json rồi khởi động lại (Tk không có cơ chế
        theme động như CSS nên phải dựng lại widget để màu đồng bộ)."""
        new = theme.toggle()
        try:
            theme.set_mode(new)
        except Exception as e:                   # noqa: BLE001
            self.log(f"Không đổi được giao diện: {e!r}", "err")
            return
        self.log(L.t("Giao diện: {m} — khởi động lại…").format(
            m=("Tối" if new == "dark" else "Sáng")), "ok")
        self.root.after(150, self.restart_app)

    def _toggle_language(self) -> None:
        """Chuyển VI ↔ EN (giữ hành vi cũ: cần khởi động lại)."""
        try:
            nxt = "en" if L.current() == "vi" else "vi"
            L.set_lang(nxt)
            self.log(L.t("Ngôn ngữ: {x} — khởi động lại…").format(x=nxt.upper()), "ok")
            self.root.after(150, self.restart_app)
        except Exception as e:                   # noqa: BLE001
            self.log(f"Không đổi được ngôn ngữ: {e!r}", "err")

    # ---- nhật ký dùng chung cho cả 3 tab ------------------------------------
    def _build_shared_log(self):
        """Khung nhật ký ở ĐÁY ứng dụng: 3 dòng khi thu gọn, có nút mở rộng.

        Mặc định 3 dòng để không chiếm chỗ của bảng/biểu đồ; dòng lỗi luôn
        nổi bật (biểu tượng ✕ + màu + nền) nên khi thu gọn vẫn thấy.
        """
        pal, f = self.pal, self.fnt
        wrap = ttk.Frame(self.root)
        wrap.pack(side="bottom", fill="x", padx=6, pady=(0, 6))
        head = ttk.Frame(wrap)
        head.pack(fill="x")
        ttk.Label(head, text=L.t("Nhật ký hoạt động").upper(),
                  style="H2.TLabel").pack(side="left", padx=(2, 8), pady=(2, 2))
        self.log_count = ttk.Label(head, text="", style="Muted.TLabel")
        self.log_count.pack(side="left")
        self.btn_log = ttk.Button(head, text=L.t("Mở rộng ▾"), width=12,
                                  style="Ghost.TButton", command=self.toggle_log)
        self.btn_log.pack(side="right", pady=(0, 2))

        box = tk.Frame(wrap, highlightthickness=1,
                       highlightbackground=pal["line"], bd=0)
        box.pack(fill="x", pady=(2, 0))
        self.log_text = tk.Text(box, height=5, wrap="word", relief="flat",
                                borderwidth=0, state="disabled", font=f["log"], padx=theme.sp(8), pady=theme.sp(4))
        theme.paint_tk(self.log_text, "log")
        sb = ttk.Scrollbar(box, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=sb.set)
        self.log_text.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.log_text.tag_configure("err", foreground=pal["err"])
        self.log_text.tag_configure("ok", foreground=pal["ok"])
        self.log_text.tag_configure("warn", foreground=pal["warn"])
        self.log_text.tag_configure("time", foreground=pal["muted"])
        self.log_expanded = False

    def toggle_log(self) -> None:
        """Thu gọn (5 dòng) ↔ mở rộng (16 dòng)."""
        self.log_expanded = not getattr(self, "log_expanded", False)
        try:
            self.log_text.configure(height=16 if self.log_expanded else 5)
            self.btn_log.configure(
                text=L.t("Thu gọn ▴") if self.log_expanded else L.t("Mở rộng ▾"))
        except tk.TclError:
            pass

    def log_lines(self) -> list[str]:
        return self.log_text.get("1.0", "end").splitlines()

    # ---- TAB 1: ghi tự động

    def _build_settings_tab(self):
        """Tab 3: hồ sơ trạm/kính · danh mục & công cụ · nơi lưu & ngôn ngữ ·
        chẩn đoán phần cứng · kiểm chứng (giữ đủ tính năng của tab 4/5 cũ)."""
        import psr_site as _site
        # Notebook ẨN dải tab (style Nav.TNotebook) + menu dọc bên trái.
        # Vẫn là con TRỰC TIẾP của tab_set và vẫn đủ 5 tab (bộ test kiểm tra).
        sub = ttk.Notebook(self.tab_set, style="Nav.TNotebook")

        # (a) HỒ SƠ TRẠM / KÍNH -------------------------------------------
        f_prof = ttk.Frame(sub)
        sub.add(f_prof, text=L.t("  Hồ sơ trạm/kính  "))
        prof = _site.active_profile()
        tel = prof.telescope
        box = ttk.LabelFrame(f_prof, text=L.t("Trạm & kính (hồ sơ)"))
        box.pack(fill="x", padx=8, pady=8)
        rows = [
            ("Trạm", f"{prof.site.name} · lat {prof.site.lat_deg:.4f}° · "
                     f"lon {prof.site.lon_deg:.4f}° · UTC{prof.site.tz_offset_h:+.0f}"),
            ("Kính", f"{tel.name} · D {tel.diameter_m} m · η {tel.efficiency} · "
                     f"A_eff {tel.a_eff_m2():.2f} m² · {tel.mount}"),
            ("Gain", f"{tel.gain_k_per_jy()*1e3:.2f} mK/Jy · HPBW = {tel.hpbw_k}·λ/D"),
            ("Hồ sơ", f"{prof.id}  ({_site.profiles_dir()})"),
        ]
        for r, (k, v) in enumerate(rows):
            ttk.Label(box, text=k + ":", width=10).grid(row=r, column=0, sticky="w",
                                                        padx=6, pady=2)
            ttk.Label(box, text=v).grid(row=r, column=1, sticky="w", padx=6)
        cols = ("band", "fc", "bw", "tsys", "sefd", "hpbw")
        tv = ttk.Treeview(box, columns=cols, show="headings", height=len(prof.bands))
        for c, ttl, w in zip(cols, ("Băng", "fc (MHz)", "B (MHz)", "T_sys (K)",
                                    "SEFD (kJy)", "HPBW (°)"), (90, 90, 90, 90, 100, 90)):
            tv.heading(c, text=ttl)
            tv.column(c, width=w, anchor="w")
        for b in prof.bands:
            tv.insert("", "end", values=(b.id, f"{b.fc_mhz:.0f}", f"{b.bw_mhz:g}",
                                         f"{b.tsys_k:g}",
                                         f"{b.sefd_jy(tel)/1e3:.1f}",
                                         f"{b.hpbw_deg(tel):.2f}"))
        tv.grid(row=len(rows), column=0, columnspan=2, sticky="we", padx=6, pady=(8, 4))
        ttk.Label(f_prof, text=L.t("Đổi hồ sơ: đặt biến môi trường PSR_PROFILE=<file.json> "
                                   "hoặc sửa configs/. Không cần sửa code."),
                  foreground="#5f5f5f", wraplength=900, justify="left").pack(
            anchor="w", padx=12, pady=(0, 8))

        # (b) DANH MỤC & CÔNG CỤ KẾ HOẠCH --------------------------------
        f_cat = ttk.Frame(sub)
        sub.add(f_cat, text=L.t("  Danh mục & công cụ  "))
        self._build_targets_tab(parent=f_cat)

        # (c) NƠI LƯU & NGÔN NGỮ ----------------------------------------
        f_io = ttk.Frame(sub)
        sub.add(f_io, text=L.t("  Nơi lưu & ngôn ngữ  "))
        self._build_dirs_lang(f_io)
        gate = ttk.LabelFrame(f_io, text=L.t("Ngưỡng gatekeeper (ingest_guard)"))
        gate.pack(fill="x", padx=8, pady=8)
        _g = chr(10).join([
            "ADC < 0,01 % → OK · 0,01–0,5 % → WARN (dùng median/MAD) · > 0,5 % → ABORT",
            "Spectral Kurtosis: ngoài 1 ± 3σ_SK (σ_SK ≈ √(4/M), M ≥ 1000) → cờ RFI",
            "Radiometer: σ/μ lệch > 20 % so với 1/√(Δf·τ) → GAIN_DRIFT",
            "Bandpass trượt 600 s · ΔT_LNA > 2 °C → rút về 180 s",
            "T_sys > 1,5× chuẩn → DEGRADED (kiểm tra Mặt Trời + elevation < 15°)",
        ])
        ttk.Label(gate, justify="left", wraplength=940, text=_g).pack(
            anchor="w", padx=10, pady=8)

        # (d) CHẨN ĐOÁN PHẦN CỨNG (tab 4 cũ) ---------------------------
        f_hw = ttk.Frame(sub)
        sub.add(f_hw, text=L.t("  Phần cứng  "))
        self._build_hw_tab(parent=f_hw)

        # (e) KIỂM CHỨNG & CORPUS (tab 5 cũ) ---------------------------
        f_chk = ttk.Frame(sub)
        sub.add(f_chk, text=L.t("  Kiểm chứng  "))
        self._build_check_tab(parent=f_chk)
        self._build_settings_nav(sub)

    def _build_settings_nav(self, sub) -> None:
        """Menu điều hướng DỌC (≥190–210 px) cho tab Cài đặt & Công cụ.

        Notebook vẫn giữ 5 tab nhưng bị ẩn dải tab; bấm mục ở đây để chuyển.
        Cột rộng cố định + padding dọc để chữ không chạm mép (đúng góp ý).
        """
        self.nav = tk.Frame(self.tab_set, background=self.pal["surface"],
                            width=theme.sp(210),
                            highlightthickness=1,
                            highlightbackground=self.pal["line"])
        self.nav.pack(side="left", fill="y", padx=(0, theme.sp(6)))
        self.nav.pack_propagate(False)          # giữ đúng 210 px, không co theo chữ
        ttk.Label(self.nav, text=L.t("MỤC"), style="CardH2.TLabel").pack(
            anchor="w", padx=theme.sp(12), pady=(theme.sp(10), theme.sp(6)))
        self._nav_btns = []
        for i in range(sub.index("end")):
            title = sub.tab(i, "text").strip()
            b = ttk.Button(self.nav, text=title, style="Ghost.TButton",
                           command=lambda k=i: sub.select(k))
            b.pack(fill="x", padx=theme.sp(6), pady=theme.sp(2), ipady=theme.sp(6))
            self._nav_btns.append(b)
        sub.bind("<<NotebookTabChanged>>", lambda _e: self._sync_nav(sub))
        sub.pack(side="left", fill="both", expand=True, padx=(0, theme.sp(6)))
        self.root.after_idle(lambda: self._sync_nav(sub))

    def _sync_nav(self, sub) -> None:
        """Tô đậm mục điều hướng đang chọn (không dựa vào màu đơn thuần:
        mục đang chọn có nền + viền nhấn và chữ đậm)."""
        try:
            cur = sub.index("current")
        except (tk.TclError, AttributeError):
            return
        for i, b in enumerate(getattr(self, "_nav_btns", [])):
            try:
                b.configure(style="NavSel.TButton" if i == cur
                            else "Ghost.TButton")
            except tk.TclError:
                pass

    def _build_plan_table(self, parent):
        """Bảng kế hoạch đêm nay — CỘT TRÁI (grid), có thanh cuộn dọc.

        Chọn dòng → điền mục tiêu + DM sang cột cấu hình bên phải.
        """
        box = ttk.LabelFrame(parent, text=L.t("Kế hoạch đêm nay"))
        box.grid(row=0, column=0, sticky="nsew")
        bar = ttk.Frame(box)
        bar.pack(fill="x", padx=theme.sp(6), pady=(theme.sp(4), 0))
        ttk.Label(bar, text=L.t("Hồ sơ:"), style="CardMuted.TLabel").pack(
            side="left", padx=(2, 4))
        self.plan_profile_lbl = ttk.Label(bar, text="", style="CardMuted.TLabel")
        self.plan_profile_lbl.pack(side="left")
        ttk.Button(bar, text=L.t("Làm mới"), style="Ghost.TButton",
                   command=self.refresh_plan).pack(side="right")

        wrap = ttk.Frame(box)
        wrap.pack(fill="both", expand=True, padx=theme.sp(6), pady=theme.sp(6))
        cols = ("tgt", "tr", "alt", "snr", "need", "dmmax")
        self.plan_tree = ttk.Treeview(wrap, columns=cols, show="headings",
                                      height=7, selectmode="browse")
        heads = ("Mục tiêu", "Transit", "Alt", "SNR/giờ", "→ SNR 8", "DM max")
        # width = bề rộng KHỞI ĐIỂM, minwidth = sàn; stretch=True để Treeview tự
        # chia phần dư. Trước đây cộng dồn bề rộng cố định nên ở 130 % bề rộng
        # vượt khung → cột cuối (dm_max) bị cắt mất.
        widths = tuple(theme.sp(v) for v in (108, 58, 60, 66, 70, 76))
        mins = tuple(theme.sp(v) for v in (86, 52, 54, 58, 62, 66))
        anchors = ("w", "center", "center", "e", "e", "e")
        for c, ttl, w, mn, anc in zip(cols, heads, widths, mins, anchors):
            self.plan_tree.heading(c, text=ttl)
            self.plan_tree.column(c, width=w, minwidth=mn, anchor=anc,
                                  stretch=True)
        sb = ttk.Scrollbar(wrap, orient="vertical", command=self.plan_tree.yview)
        self.plan_tree.configure(yscrollcommand=sb.set)
        self.plan_tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.plan_tree.bind("<<TreeviewSelect>>", self._on_plan_select)
        self.plan_rows = []

    def refresh_plan(self):
        """Tính lại bảng kế hoạch từ hồ sơ trạm/kính + flux ATNF (không cần SDR)."""
        import psr_site as _site
        import psr_targets as _T
        import psr_sensitivity as _S
        from datetime import datetime as _dt
        prof = _site.active_profile()
        tel = prof.telescope
        band = prof.band("lband") or prof.bands[0]
        sefd = band.sefd_jy(tel)
        hpbw = tel.hpbw_deg(band.fc_mhz)
        now = _dt.now()
        self.plan_tree.delete(*self.plan_tree.get_children())
        self.plan_rows = []
        for t in _T.all_pulsars():
            if t.get("P") is None or t.get("dm") is None:
                continue
            try:
                s_jy, w_s = _T.pick_flux(t, band.fc_mhz)
                snr_h = (_S.snr_fold(s_jy, sefd, band.bw_mhz * 1e6, 3600.0,
                                     t["P"], w_s) if s_jy else 0.0)
                tr = _T.transit_local(t["ra"], now).strftime("%H:%M")
                alt = _T.alt_max(t["dec"])
                dmmax = max(100.0, 1.5 * float(t["dm"]))
                if snr_h > 0:
                    need_s = (8.0 / snr_h) ** 2 * 3600.0
                    need = ("{:.0f} phút".format(need_s / 60) if need_s < 5400
                            else "{:.1f} h".format(need_s / 3600))
                else:
                    need = "—"
                iid = self.plan_tree.insert("", "end", values=(
                    t["name"], tr, "{:.1f}°".format(alt), "{:.1f}".format(snr_h),
                    need, "{:.0f}".format(dmmax)))
                self.plan_rows.append(dict(iid=iid, name=t["name"],
                                           dm=float(t["dm"]), snr_h=snr_h))
            except Exception:
                continue
        if self.plan_rows:
            first = self.plan_rows[0]["iid"]
            self.plan_tree.selection_set(first)
            self.plan_tree.focus(first)
            self._on_plan_select(None)
        self.plan_profile_lbl.configure(
            text="{} · {} {:.0f} MHz · B {:g} MHz · SEFD {:.1f} kJy · HPBW {:.2f}°".format(
                prof.id, band.id, band.fc_mhz, band.bw_mhz, sefd / 1e3, hpbw))

    def _on_plan_select(self, _evt=None):
        sel = self.plan_tree.selection()
        if not sel:
            return
        row = None
        for r in self.plan_rows:
            if r["iid"] == sel[0]:
                row = r
                break
        if row is None:
            return
        self.rec_target.set(row["name"])
        self.rec_dm.delete(0, "end")
        self.rec_dm.insert(0, "{:.3f}".format(row["dm"]))
        self.log("Kế hoạch → {} · DM {:.3f} · SNR {:.1f}/h".format(
            row["name"], row["dm"], row["snr_h"]))

    def _build_recorder_tab(self):
        """Tab 1 — BỐ CỤC 2 CỘT (Wireframe A): bảng mục tiêu bên trái (55 %),
        cấu hình + cụm nút ghi bên phải (45 %). Nhờ vậy cả bảng + nhật ký 3
        dòng ở đáy vừa khung 1366×768 mà không phải cuộn.
        """
        body = ttk.Frame(self.tab_plan)
        body.pack(fill="both", expand=True, padx=theme.sp(6), pady=theme.sp(6))
        body.columnconfigure(0, weight=55, minsize=theme.sp(500))
        body.columnconfigure(1, weight=45, minsize=theme.sp(420))
        body.rowconfigure(0, weight=1)

        self._build_plan_table(body)          # cột 0

        right = ttk.LabelFrame(body, text=L.t("Cấu hình & ghi"))
        right.grid(row=0, column=1, sticky="nsew", padx=(theme.sp(8), 0))

        # Footer pack TRƯỚC canvas: pack cấp bề ngang theo thứ tự, nếu pack sau
        # thì chỉ còn phần hẹp bên phải (cụm nút bị bóp lại).
        _footer = ttk.Frame(right, style="Card.TFrame")
        _footer.pack(side="bottom", fill="x", padx=theme.sp(8), pady=theme.sp(6))

        # Vùng cuộn dọc: ở 1366×710 @130 % nội dung cột phải cao hơn khung,
        # nếu không cuộn thì cụm nút và dòng dung lượng bị cắt mất.
        _cv = tk.Canvas(right, highlightthickness=0, bd=0,
                        background=self.pal["surface"])
        _vsb = ttk.Scrollbar(right, orient="vertical", command=_cv.yview)
        _cv.configure(yscrollcommand=_vsb.set)
        _cv.pack(side="left", fill="both", expand=True)
        _vsb.pack(side="right", fill="y")
        pf = ttk.Frame(_cv)
        _win = _cv.create_window((0, 0), window=pf, anchor="nw")
        pf.bind("<Configure>",
                lambda _e: _cv.configure(scrollregion=_cv.bbox("all")))
        _cv.bind("<Configure>",
                 lambda e: _cv.itemconfigure(_win, width=e.width))
        # lăn chuột khi trỏ vào vùng cấu hình
        def _wheel(ev):
            try:
                _cv.yview_scroll(-1 if ev.delta > 0 else 1, "units")
            except tk.TclError:
                pass
            return "break"
        _cv.bind("<Enter>", lambda _e: _cv.bind_all("<MouseWheel>", _wheel))
        _cv.bind("<Leave>", lambda _e: _cv.unbind_all("<MouseWheel>"))
        pf.columnconfigure(1, weight=1)

        # ------------------------------------------------ nhóm CƠ BẢN
        ttk.Label(pf, text=L.t("MỤC TIÊU"), style="CardH2.TLabel").grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, theme.sp(4)))
        self.rec_target = ttk.Combobox(pf, values=[], width=16)
        # CHO GÕ TAY: quan sát nguồn ngoài danh mục, không bị khoá cứng
        self.rec_target.configure(state="normal")
        self.rec_target.set("B0950+08")
        self.rec_target.grid(row=1, column=0, columnspan=2, sticky="we",
                             pady=(0, theme.sp(6)))
        ttk.Button(pf, text=L.t("＋ Thêm…"), style="Ghost.TButton",
                   command=self.manage_targets).grid(
            row=1, column=2, padx=(theme.sp(4), 0))

        # DM · Băng · Thời lượng trên CÙNG một hàng (tiết kiệm chiều dọc —
        # ở 1366×710 @130 % nếu tách 3 hàng thì cụm nút bị đẩy ra ngoài khung)
        _f3 = ttk.Frame(pf)
        _f3.grid(row=2, column=0, columnspan=3, sticky="we", pady=(0, theme.sp(4)))
        for _i, (_lab, _w) in enumerate(((L.t("DM tham chiếu"), 9),
                                        (L.t("Băng (MHz)"), 6),
                                        (L.t("Thời lượng (giờ)"), 7))):
            ttk.Label(_f3, text=_lab, style="CardMuted.TLabel").grid(
                row=0, column=_i, sticky="w", padx=(0, theme.sp(8)))
        self.rec_dm = ttk.Entry(_f3, width=9)
        self.rec_dm.grid(row=1, column=0, sticky="w", padx=(0, theme.sp(8)))
        self.rec_band = ttk.Combobox(_f3, values=["423", "1420"], width=6,
                                     state="readonly")
        self.rec_band.set("423")
        self.rec_band.grid(row=1, column=1, sticky="w", padx=(0, theme.sp(8)))
        self.rec_hours = ttk.Spinbox(_f3, from_=0.5, to=8.0, increment=0.5, width=7)
        self.rec_hours.set(4.5)
        self.rec_hours.grid(row=1, column=2, sticky="w")

        # ------------------------------------------------ nhóm NÂNG CAO (thu gọn)
        self.adv_open = False
        adv_bar = ttk.Frame(pf)
        adv_bar.grid(row=3, column=0, columnspan=3, sticky="we")
        self.btn_adv = ttk.Button(adv_bar, text=L.t("▸ Nâng cao"),
                                  style="Ghost.TButton", command=self.toggle_advanced)
        self.btn_adv.pack(side="left")
        self.adv_summary = ttk.Label(adv_bar, text="", style="CardMuted.TLabel")
        self.adv_summary.pack(side="left", padx=(theme.sp(8), 0))

        self.adv_frame = ttk.Frame(pf)
        self.adv_frame.columnconfigure(1, weight=1)
        ttk.Label(self.adv_frame, text=L.t("Kênh"),
                  style="CardMuted.TLabel").grid(row=0, column=0, sticky="w")
        self.rec_nchan = ttk.Spinbox(self.adv_frame, from_=16, to=512,
                                     increment=16, width=8)
        self.rec_nchan.set(64)
        self.rec_nchan.grid(row=0, column=1, sticky="w", padx=(theme.sp(6), 0))
        ttk.Label(self.adv_frame, text=L.t("tsamp (µs)"),
                  style="CardMuted.TLabel").grid(row=0, column=2, sticky="w",
                                                 padx=(theme.sp(10), 0))
        self.rec_tsamp = ttk.Spinbox(self.adv_frame, from_=64, to=2000,
                                     increment=64, width=8)
        self.rec_tsamp.set(256)
        self.rec_tsamp.grid(row=0, column=3, sticky="w", padx=(theme.sp(6), 0))

        # ---------------------------- NGUỒN DỮ LIỆU: 3 trạng thái, có biểu tượng
        _nf = ttk.Frame(pf)
        _nf.grid(row=4, column=0, columnspan=3, sticky="we",
                 pady=(theme.sp(6), theme.sp(2)))
        ttk.Label(_nf, text=L.t("NGUỒN DỮ LIỆU"), style="CardH2.TLabel").pack(
            side="left")
        ttk.Button(_nf, text=L.t("Dò lại"), style="Ghost.TButton",
                   command=self.refresh_hw_status).pack(side="right")
        _sf = ttk.Frame(pf)
        _sf.grid(row=5, column=0, columnspan=3, sticky="w",
                 pady=(theme.sp(2), theme.sp(2)))
        self.rec_source = SegmentedChoice(
            _sf, values=list(SOURCE_MODES.values()),
            labels=(L.t("Tự động"), L.t("Mô phỏng"), L.t("SDR thật")),
            on_change=lambda _v: (self.refresh_hw_status()
                                  if hasattr(self, "rec_hw_label") else None))
        self.rec_source.set(SOURCE_MODES["auto"])
        self.rec_source.pack(side="left")
        self.rec_hw_label = ttk.Label(pf, text=L.t("… đang dò thiết bị"),
                                      style="CardMuted.TLabel",
                                      wraplength=theme.sp(420), justify="left")
        self.rec_hw_label.grid(row=6, column=0, columnspan=3, sticky="w",
                               pady=(0, theme.sp(4)))

        # ---------------------------------- cụm nút: MỘT nút chính + Dừng riêng
        # ---- FOOTER dính đáy: cụm nút luôn nhìn thấy, không phải cuộn
        ttk.Separator(_footer, orient="horizontal").pack(fill="x",
                                                         pady=(0, theme.sp(6)))
        act = ttk.Frame(_footer)
        act.pack(fill="x")
        self.btn_rec = ttk.Button(act, text=L.t("▶ Bắt đầu ghi"),
                                  style="Primary.TButton", command=self.start_recording)
        self.btn_rec.pack(side="left")
        self.btn_stop = ttk.Button(act, text=L.t("■ Dừng"), style="Stop.TButton",
                                   command=self.stop_recording, state="disabled")
        self.btn_stop.pack(side="left", padx=(theme.sp(6), 0))


        act2 = ttk.Frame(_footer)
        act2.pack(fill="x", pady=(theme.sp(4), 0))
        ttk.Button(act2, text=L.t("Phân tích file vừa ghi"), style="Next.TButton",
                   command=self.analyze_last_recorded).pack(
            side="left", fill="x", expand=True)
        ttk.Button(act2, text=L.t("Mở thư mục"), style="Ghost.TButton",
                   command=lambda: self.open_dir(DATA_DIR)).pack(
            side="right", padx=(theme.sp(6), 0))
        # chỉ hiện khi đã có file vừa ghi (xem _after_recorded)
        self.btn_to_det = ttk.Button(act2, text=L.t("→ Sang Tab 2"),
                                     style="Ghost.TButton", command=self.goto_detect)
        self.btn_to_det.pack_forget()

        self.rec_disk = ttk.Label(_footer, text="", style="CardMuted.TLabel")
        self.rec_disk.pack(anchor="w", pady=(theme.sp(4), 0))

        self.refresh_target_list(select="B0950+08")
        self.rec_source.set(SOURCE_MODES["auto"])
        self._update_adv_summary()
        self.root.after_idle(self.refresh_plan)          # bảng kế hoạch đêm nay
        self.root.after_idle(lambda: self.refresh_hw_status())
        self.root.after_idle(self._update_disk_note)

    def toggle_advanced(self) -> None:
        """Mở/thu gọn nhóm thông số ít dùng (giữ màn hình gọn)."""
        self.adv_open = not getattr(self, "adv_open", False)
        if self.adv_open:
            self.btn_adv.configure(text=L.t("▾ Nâng cao"))
            self.adv_frame.grid(row=6, column=0, columnspan=3, sticky="we",
                                pady=(theme.sp(2), theme.sp(6)))
        else:
            self.btn_adv.configure(text=L.t("▸ Nâng cao"))
            self.adv_frame.grid_forget()
        self._update_adv_summary()

    def _update_adv_summary(self) -> None:
        if not hasattr(self, "adv_summary"):
            return
        try:
            txt = L.t("kênh {n} · {t} µs").format(n=self.rec_nchan.get(),
                                                 t=self.rec_tsamp.get())
            self.adv_summary.configure(
                text="" if getattr(self, "adv_open", False) else txt)
        except tk.TclError:
            pass

    def _update_disk_note(self) -> None:
        """Ghi chú dung lượng cạnh nút ghi (khỏi phải mở hộp thoại)."""
        try:
            import shutil as _sh
            free = _sh.disk_usage(psr_paths.results_dir()).free
            need = 5.0 * 3600 * 0.25e6          # ~0,25 MB/s trong 5 giờ
            self.rec_disk.configure(
                text=L.t("Còn trống {f:.0f} GB · cần ~{n:.0f} GB cho 5 h").format(
                    f=free / 1e9, n=need / 1e9))
        except Exception:                        # noqa: BLE001
            pass


    # ---- TAB 2: phát hiện
    def _build_dirs_lang(self, parent):
        """Nơi lưu + ngôn ngữ (tab Cài đặt)."""
        # ---- NƠI LƯU (chọn được, lưu vào settings.json)
        sf = ttk.LabelFrame(parent, text=L.t("Nơi lưu dữ liệu (có thể chọn ổ khác, ví dụ SSD ngoài)"))
        sf.pack(fill="x", padx=8, pady=8)
        self.dir_vars = {}
        for r, (key, label) in enumerate((("data_dir", "Dữ liệu thô:"),
                                          ("results_dir", "Kết quả:"))):
            ttk.Label(sf, text=label, width=12).grid(row=r, column=0, sticky="w",
                                                     padx=(6, 2), pady=3)
            var = tk.StringVar(value=self._dir_value(key))
            ent = ttk.Entry(sf, textvariable=var, width=64)
            ent.grid(row=r, column=1, sticky="we", padx=4, pady=3)
            ttk.Button(sf, text=L.t("Chọn…"), width=8,
                       command=lambda k=key, v=var: self.choose_dir(k, v)).grid(
                row=r, column=2, padx=4)
            ttk.Button(sf, text=L.t("Mở"), width=5,
                       command=lambda k=key: self.open_dir(self._dir_value(k))).grid(
                row=r, column=3, padx=(0, 6))
            self.dir_vars[key] = var
        ttk.Button(sf, text=L.t("Áp dụng"), width=10,
                   command=self.apply_dirs).grid(row=0, column=4, rowspan=2, padx=6)
        # ---- ngôn ngữ (áp dụng sau khi khởi động lại) -------------------
        ttk.Label(sf, text=L.t("Ngôn ngữ / Language:"), width=20).grid(
            row=3, column=0, sticky="w", padx=(6, 2), pady=(4, 2))
        self.lang_box = ttk.Combobox(
            sf, values=[L.LANG_NAMES[k] for k in L.LANGS], state="readonly", width=16)
        self.lang_box.set(L.LANG_NAMES.get(L.current(), "Tiếng Việt"))
        self.lang_box.grid(row=3, column=1, sticky="w", padx=4)
        self.lang_box.bind("<<ComboboxSelected>>", self.on_lang_change)
        # ---- độ phóng giao diện (vẫn vẽ pixel nguyên nên KHÔNG bị mờ) ----
        ttk.Label(sf, text=L.t("Độ phóng giao diện:"), width=20).grid(
            row=4, column=0, sticky="w", padx=(6, 2), pady=(2, 2))
        self.ui_scale_box = ttk.Combobox(
            sf, values=["100 %", "115 %", "130 %"], state="readonly", width=10)
        _cur = f"{theme.scale() * 100:.0f} %"
        self.ui_scale_box.set(_cur if _cur in ("100 %", "115 %", "130 %")
                              else "100 %")
        self.ui_scale_box.grid(row=4, column=1, sticky="w", padx=4)
        self.ui_scale_box.bind("<<ComboboxSelected>>", self.on_ui_scale_change)
        ttk.Button(sf, text=L.t("Áp dụng"), width=8, style="Ghost.TButton",
                   command=lambda: self.on_ui_scale_change()).grid(
            row=4, column=2, sticky="w", padx=4)
        ttk.Label(sf, text=L.t("(ghi vào settings.json cạnh app; có hiệu lực ngay, không cần khởi động lại)"),
                  foreground="#5f5f5f").grid(row=2, column=0, columnspan=5,
                                             sticky="w", padx=6, pady=(2, 4))


    def _build_detect_tab(self):
        # ---- dải bước: Chọn dữ liệu → Kiểm tra → Cấu hình → Phân tích → Kết quả
        self._build_detect_steps()

        f = ttk.LabelFrame(self.tab_det,
                           text=L.t("Phát hiện pulsar trên file filterbank (.fil)"))
        f.pack(fill="x", padx=8, pady=(theme.sp(6), theme.sp(6)))

        ttk.Button(f, text=L.t("Chọn file .fil…"), command=self.pick_fil).grid(
            row=0, column=0, padx=4, pady=4)
        self.det_file = ttk.Entry(f, width=64)
        self.det_file.grid(row=0, column=1, columnspan=3, padx=4, sticky="we")

        ttk.Label(f, text=L.t("DM tham chiếu:")).grid(row=1, column=0, sticky="w", padx=4)
        self.det_dm = ttk.Entry(f, width=12)
        self.det_dm.insert(0, "26.7641")
        self.det_dm.grid(row=1, column=1, padx=4, sticky="w")

        ttk.Label(f, text=L.t("Chu kỳ P (s):"), style="CardMuted.TLabel").grid(
            row=1, column=2, sticky="w", padx=(theme.sp(10), 4))
        self.det_p = ttk.Entry(f, width=12)
        self.det_p.insert(0, "")          # bỏ trống = dò chu kỳ mù (M3)
        self.det_p.grid(row=1, column=3, padx=4, sticky="w")
        # Số kênh IQ + checkbox xuống HÀNG RIÊNG: trước đây chúng chiếm cùng
        # ô grid với nhãn nên chữ bị đè lên nhau.
        row2 = ttk.Frame(f)
        row2.grid(row=2, column=0, columnspan=6, sticky="we", padx=4,
                  pady=(0, theme.sp(4)))
        ttk.Label(row2, text=L.t("Số kênh IQ:"),
                  style="CardMuted.TLabel").pack(side="left")
        self.det_iqn = ttk.Spinbox(row2, from_=32, to=2048, increment=64, width=6)
        self.det_iqn.set(256)
        self.det_iqn.pack(side="left", padx=(4, theme.sp(12)))
        self.det_search = tk.BooleanVar(value=True)
        ttk.Checkbutton(row2, text=L.t("dò chu kỳ mù (FFT) khi không có P"),
                        variable=self.det_search).pack(side="left")

        # ---- ingest_guard: TÓM TẮT luôn hiện, CHI TIẾT mở rộng khi cần
        self.guard_box = ttk.LabelFrame(
            self.tab_det, text=L.t("ingest_guard — dữ liệu vào đã được nhận dạng thế nào"))
        self.guard_box.pack(fill="x", padx=8, pady=(0, theme.sp(8)))
        _gh = ttk.Frame(self.guard_box)
        _gh.pack(fill="x", padx=theme.sp(6), pady=(theme.sp(4), 0))
        self.guard_summary = ttk.Label(_gh, text=L.t("chưa có dữ liệu"),
                                       style="CardMuted.TLabel")
        self.guard_summary.pack(side="left")
        self.guard_open = False
        self.btn_guard = ttk.Button(_gh, text=L.t("Chi tiết ▾"), style="Ghost.TButton",
                                    command=self.toggle_guard)
        self.btn_guard.pack(side="right")
        self.guard_detail = ttk.Frame(self.guard_box)
        self.guard_lbl = {}
        _grows = (("fmt", "Định dạng"), ("stage", "Stage"), ("dt", "Δt mẫu"),
                  ("bp", "Bandpass"), ("meta", "Metadata"),
                  ("adc", "ADC"), ("sk", "Spectral kurtosis"),
                  ("rad", "Radiometer"), ("gap", "Gap / đồng hồ"), ("tags", "Nhãn"))
        for _r, (_k, _ttl) in enumerate(_grows):
            ttk.Label(self.guard_detail, text=_ttl + ":", width=17,
                      style="CardMuted.TLabel").grid(
                row=_r // 2, column=(_r % 2) * 2, sticky="w", padx=6, pady=2)
            _lbl = ttk.Label(self.guard_detail, text="—", style="Card.TLabel")
            _lbl.grid(row=_r // 2, column=(_r % 2) * 2 + 1, sticky="w", padx=6)
            self.guard_lbl[_k] = _lbl

        # ---- M3: dò chu kỳ mù (FFT) — Top-N ứng viên
        self.m3_box = ttk.LabelFrame(
            self.tab_det, text=L.t("M3 — dò chu kỳ mù (FFT + sàng hài)"))
        self.m3_box.pack(fill="x", padx=8, pady=(0, 8))
        self.m3_lbl = ttk.Label(self.m3_box,
                                text=L.t("chưa chạy — bấm Chạy phát hiện"),
                                style="CardMuted.TLabel")
        self.m3_lbl.pack(side="left", padx=8, pady=4)
        ttk.Button(self.m3_box, text=L.t("Mở hình fig3"),
                   command=lambda: self.open_result_file("fig3_period.png")).pack(
            side="right", padx=6, pady=4)

        bf = ttk.Frame(self.tab_det)
        bf.pack(fill="x", padx=8)
        self.btn_det = ttk.Button(bf, text=L.t("▶ Chạy phát hiện"), command=self.run_detect)
        self.btn_det.pack(side="left", padx=4, pady=4)
        ttk.Button(bf, text=L.t("Mở báo cáo TXT"),
                   command=self.open_report).pack(side="left", padx=4)
        ttk.Button(bf, text=L.t("Mở metrics JSON"),
                   command=self.open_metrics).pack(side="left", padx=4)
        ttk.Button(bf, text=L.t("Mở thư mục kết quả của lần chạy"),
                   command=self.open_last_result_dir).pack(side="left", padx=4)

        # ---- hiển thị biểu đồ
        vf = ttk.LabelFrame(self.tab_det, text=L.t("Biểu đồ kết quả"))
        vf.pack(fill="both", expand=True, padx=8, pady=8)
        top = ttk.Frame(vf)
        top.pack(fill="x")
        ttk.Label(top, text=L.t("Hình:")).pack(side="left", padx=4)
        self.det_figpick = ttk.Combobox(top, values=[], width=42)
        self.det_figpick.pack(side="left", padx=4)
        self.det_figpick.bind("<<ComboboxSelected>>", self.show_selected_figure)
        ttk.Button(top, text=L.t("Mở bằng trình xem ảnh"),
                   command=self.open_figure_external).pack(side="left", padx=4)
        ttk.Button(top, text=L.t("Mở SVG (zoom ∞)"),
                   style="Next.TButton",
                   command=self.open_figure_vector).pack(side="left", padx=4)

        from matplotlib.figure import Figure
        from matplotlib.backends.backend_tkagg import (
            FigureCanvasTkAgg, NavigationToolbar2Tk)
        self.det_fig = Figure(figsize=(9, 5.2))
        self.det_canvas = FigureCanvasTkAgg(self.det_fig, master=vf)
        self.det_canvas.get_tk_widget().pack(fill="both", expand=True)
        # Thanh công cụ matplotlib: zoom khung, pan, lưu — zoom trong app là
        # phóng ẢNH ĐÃ VẼ; muốn zoom vô hạn thì mở bản SVG/PDF (nút bên trên).
        try:
            self.det_toolbar = NavigationToolbar2Tk(
                self.det_canvas, vf, pack_toolbar=False)
            self.det_toolbar.update()
            self.det_toolbar.pack(side="bottom", fill="x")
        except Exception:                 # noqa: BLE001 — thiếu backend thì thôi
            self.det_toolbar = None
        self._refresh_figure_list()

    def _build_detect_steps(self) -> None:
        """Dải bước của Tab 2 (đọc là biết đang ở đâu, không cần đoán).

        Mỗi bước có BIỂU TƯỢNG + CHỮ: ✔ xong · ▸ đang làm · ○ chưa tới.
        """
        self.det_steps = (
            L.t("Chọn dữ liệu"), L.t("Kiểm tra đầu vào"), L.t("Cấu hình"),
            L.t("Phân tích"), L.t("Kết quả"))
        bar = ttk.Frame(self.tab_det)
        bar.pack(fill="x", padx=theme.sp(6), pady=(theme.sp(6), 0))
        self.det_step_lbl = []
        for i, name in enumerate(self.det_steps):
            lb = ttk.Label(bar, text="○ " + name, style="Muted.TLabel")
            lb.pack(side="left", padx=(0, theme.sp(4)))
            self.det_step_lbl.append(lb)
            if i < len(self.det_steps) - 1:
                ttk.Label(bar, text="→", style="Muted.TLabel").pack(
                    side="left", padx=(0, theme.sp(4)))
        self.det_step = -1
        self.set_detect_step(0)

    def set_detect_step(self, idx: int) -> None:
        """Đánh dấu bước hiện tại: các bước trước = ✔, bước này = ▸."""
        self.det_step = max(-1, min(int(idx), len(self.det_steps) - 1))
        for i, lb in enumerate(getattr(self, "det_step_lbl", [])):
            if i < self.det_step:
                lb.configure(text="✔ " + self.det_steps[i], style="Ok.TLabel")
            elif i == self.det_step:
                lb.configure(text="▸ " + self.det_steps[i], style="H2.TLabel")
            else:
                lb.configure(text="○ " + self.det_steps[i], style="Muted.TLabel")

    def toggle_guard(self) -> None:
        """Mở/thu gọn phần chi tiết chất lượng dữ liệu."""
        self.guard_open = not getattr(self, "guard_open", False)
        if self.guard_open:
            self.guard_detail.pack(fill="x", padx=theme.sp(6),
                                   pady=(theme.sp(4), theme.sp(6)))
            self.btn_guard.configure(text=L.t("Thu gọn ▴"))
        else:
            self.guard_detail.pack_forget()
            self.btn_guard.configure(text=L.t("Chi tiết ▾"))

    # ---- TAB 3: mục tiêu
    def _build_targets_tab(self, parent=None):
        host = parent if parent is not None else host
        f = ttk.LabelFrame(host, text=L.t("Khả năng quan sát từ TP.HCM (lat 10.78°N)"))
        f.pack(fill="x", padx=8, pady=8)
        ttk.Label(f, text=L.t("Ngày (YYYY-MM-DD, bỏ trống = hôm nay):")).grid(
            row=0, column=0, padx=4, pady=4, sticky="w")
        self.tgt_date = ttk.Entry(f, width=12)
        self.tgt_date.grid(row=0, column=1, padx=4)
        ttk.Label(f, text=L.t("Băng thông (MHz):")).grid(row=0, column=2, padx=4)
        self.tgt_bw = ttk.Spinbox(f, from_=2.4, to=56, increment=1.0, width=6)
        self.tgt_bw.set(20)
        self.tgt_bw.grid(row=0, column=3, padx=4)

        bf = ttk.Frame(host)
        bf.pack(fill="x", padx=8)
        for txt, cmd in (("Giờ transit (để chảo cố định)", self.tgt_transit),
                         ("Quan sát ban ngày", self.tgt_daytime),
                         ("Bảng SNR (mọi mục tiêu) × 5 cấu hình", self.tgt_snr),
                         ("Đại lượng suy ra (B, tuổi, Ė)", self.tgt_derived),
                         ("Nguồn continuum khác", self.tgt_objects),
                         ("＋ Quản lý mục tiêu…", self.manage_targets)):
            ttk.Button(bf, text=txt, command=cmd).pack(side="left", padx=4, pady=4)

        lf = ttk.LabelFrame(host, text=L.t("Bảng kết quả"))
        lf.pack(fill="both", expand=True, padx=8, pady=8)
        self.tgt_out = tk.Text(lf, wrap="none", font=("Consolas", 9),
                               state="disabled")
        sb1 = ttk.Scrollbar(lf, command=self.tgt_out.yview)
        sb2 = ttk.Scrollbar(lf, command=self.tgt_out.xview, orient="horizontal")
        self.tgt_out.configure(yscrollcommand=sb1.set, xscrollcommand=sb2.set)
        self.tgt_out.pack(side="top", fill="both", expand=True)
        sb1.pack(side="right", fill="y")

    # ---- TAB 4: phần cứng
    def _build_hw_tab(self, parent=None):
        host = parent if parent is not None else host
        f = ttk.LabelFrame(host, text=L.t("Dự đoán chuỗi linh kiện + tự fallback"))
        f.pack(fill="x", padx=8, pady=8)
        ttk.Label(f, text=L.t("Băng:")).grid(row=0, column=0, padx=4, pady=4)
        self.hw_band = ttk.Combobox(f, values=["423", "1420"], width=6)
        self.hw_band.set("423")
        self.hw_band.grid(row=0, column=1, padx=4)
        ttk.Label(f, text=L.t("Mục đích:")).grid(row=0, column=2, padx=4)
        self.hw_goal = ttk.Combobox(f, values=["pulsar", "hi", "unattended"],
                                    width=12)
        self.hw_goal.set("pulsar")
        self.hw_goal.grid(row=0, column=3, padx=4)
        ttk.Button(f, text=L.t("Phát hiện chuỗi"), command=self.hw_detect).grid(
            row=0, column=4, padx=8)
        ttk.Button(f, text=L.t("Tự kiểm tra công thức"), command=self.hw_selfcheck).grid(
            row=0, column=5, padx=4)

        lf = ttk.LabelFrame(host, text=L.t("Kết quả"))
        lf.pack(fill="both", expand=True, padx=8, pady=8)
        self.hw_out = tk.Text(lf, wrap="none", font=("Consolas", 9),
                              state="disabled")
        sb = ttk.Scrollbar(lf, command=self.hw_out.yview)
        self.hw_out.configure(yscrollcommand=sb.set)
        self.hw_out.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

    # ---- TAB 5: kiểm chứng
    def _build_check_tab(self, parent=None):
        host = parent if parent is not None else host
        f = ttk.LabelFrame(host, text=L.t("Kiểm chứng máy móc (chạy trước khi tin kết quả)"))
        f.pack(fill="x", padx=8, pady=8)
        self.btn_self = ttk.Button(f, text=L.t("▶ Chạy selftest nhanh (21 test)"),
                                   command=self.run_selftest)
        self.btn_self.pack(side="left", padx=6, pady=6)
        ttk.Button(f, text=L.t("Pipeline mô phỏng (nhanh)"),
                   command=self.run_pipeline_quick).pack(side="left", padx=6)
        ttk.Button(f, text=L.t("Tự kiểm tra trình ghi (mock)"),
                   command=self.run_recorder_selftest).pack(side="left", padx=6)
        ttk.Button(f, text=L.t("▶ Corpus dữ liệu XẤU (data/stress)"),
                   command=self.run_stress).pack(side="left", padx=6)
        ttk.Button(f, text=L.t("Mở thư mục kết quả"),
                   command=lambda: self.open_dir(RESULTS_DIR)).pack(side="left", padx=6)
        ttk.Button(f, text=L.t("Mở tài liệu docs"),
                   command=lambda: self.open_dir(os.path.join(ROOT_DIR, "docs"))
                   ).pack(side="left", padx=6)
        # ---- công cụ RTCS: đọc phổ/continuum/scan do phần mềm POAM xuất ra
        ttk.Button(f, text=L.t("Phân tích dữ liệu RTCS…"),
                   style="Next.TButton",
                   command=self.rtcs_pick_files).pack(side="left", padx=6)

        lf = ttk.LabelFrame(host, text=L.t("Kết quả kiểm chứng"))
        lf.pack(fill="both", expand=True, padx=8, pady=8)
        self.chk_out = tk.Text(lf, wrap="none", font=("Consolas", 9),
                               state="disabled")
        sb = ttk.Scrollbar(lf, command=self.chk_out.yview)
        self.chk_out.configure(yscrollcommand=sb.set)
        self.chk_out.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

    # ---------------------------------------------------- công cụ RTCS (POAM)
    def rtcs_pick_files(self) -> None:
        """Chọn 3 tệp xuất của RTCS (không bắt buộc đủ cả 3) rồi phân tích."""
        from tkinter import filedialog
        init = os.path.join(ROOT_DIR, "..", "radio research", "RADIO DATA")
        if not os.path.isdir(init):
            init = ROOT_DIR
        files = filedialog.askopenfilenames(
            parent=self.root, initialdir=init,
            title=L.t("Chọn tệp xuất của RTCS (line / continuum / scan)"),
            filetypes=[(L.t("Tệp xuất RTCS"), "*.csv *.txt"),
                       (L.t("Tất cả"), "*.*")])
        if not files:
            return
        self.rtcs_analyse(list(files))

    def rtcs_classify(self, paths) -> dict:
        """Đoán loại tệp theo nội dung (không dựa vào tên): trả dict 3 khoá."""
        out = {}
        for p in paths:
            try:
                head = open(p, encoding="utf-8", errors="replace").read(4000)
            except OSError:
                continue
            low = head.lower()
            if "time - rtrs" in low or ("dbm - rtrs" in low):
                out.setdefault("continuum", p)
            elif "az-deg" in low or ("azimuth" in low and "rtrs" in low):
                out.setdefault("scan", p)
            elif "frequency" in low and "power" in low:
                out.setdefault("line", p)
            else:
                # dò theo dữ liệu: 3 cột số → scan; 2 cột → phổ
                n3 = n2 = 0
                for ln in head.splitlines()[1:40]:
                    c = [x for x in ln.replace(",", "\t").split("\t") if x.strip()]
                    try:
                        [float(v) for v in c]
                    except ValueError:
                        continue
                    if len(c) >= 3:
                        n3 += 1
                    elif len(c) == 2:
                        n2 += 1
                if n3 > n2:
                    out.setdefault("scan", p)
                elif n2:
                    out.setdefault("line", p)
        return out

    def rtcs_analyse(self, paths=None) -> None:
        """Chạy psr_rtcs trên các tệp đã chọn/đã truyền vào; in báo cáo vào ô kết quả."""
        import datetime

        import psr_rtcs
        if paths is None:
            paths = []
        kinds = self.rtcs_classify(paths)
        if not kinds:
            self.log(L.t("Không nhận ra tệp RTCS nào (cần line / continuum / scan)"),
                     "err")
            return
        out = os.path.join(RESULTS_DIR,
                           datetime.datetime.now().strftime("%Y%m%d_%H%M%S"),
                           "rtcs")
        self.log(L.t("RTCS: phân tích {n} tệp → {o}").format(n=len(kinds), o=out))
        try:
            res = psr_rtcs.analyse_all(line=kinds.get("line"),
                                       continuum=kinds.get("continuum"),
                                       scan=kinds.get("scan"), out_dir=out)
            txt = psr_rtcs.text_report(res)
        except Exception as exc:                 # noqa: BLE001
            self.log(f"RTCS lỗi: {exc!r}", "err")
            return
        try:
            self.chk_out.configure(state="normal")
            self.chk_out.delete("1.0", "end")
            self.chk_out.insert("end", txt)
            self.chk_out.configure(state="disabled")
        except tk.TclError:
            pass
        print(txt)
        self.log(L.t("RTCS: xong — xem báo cáo trong 'Kết quả kiểm chứng'"), "ok")
        try:
            self.open_dir(out)
        except Exception:                        # noqa: BLE001
            pass

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

    def _on_destroy(self, evt=None) -> None:
        if evt is not None and getattr(evt, "widget", None) is not self.root:
            return
        pid = getattr(self, "_poll_id", None)
        if pid:
            try:
                self.root.after_cancel(pid)
            except tk.TclError:
                pass
            self._poll_id = None

    def _poll_queue(self):
        try:
            while True:
                s = self.q.get_nowait()
                self.log(s.rstrip())
        except queue.Empty:
            pass
        except tk.TclError:            # cửa sổ đã đóng giữa chừng
            return
        try:
            while True:
                fn = self.cbq.get_nowait()
                try:
                    fn()
                except Exception as e:
                    self.log(f"Lỗi xử lý callback UI: {e!r}", "err")
        except queue.Empty:
            pass
        try:
            self._poll_id = self.root.after(120, self._poll_queue)
        except tk.TclError:
            # root đã bị destroy → KHÔNG hẹn lại nữa (nếu không Tcl báo
            # 'invalid command name "..._poll_queue"' lúc thoát)
            self._poll_id = None

    def run_bg(self, fn, *args, on_done=None, **kwargs):
        """Chạy hàm nặng trong thread; log tự động; khoá nút khi đang chạy."""
        if self.busy:
            self.log(L.t("Đang có tác vụ chạy — đợi hoàn tất trước."), "err")
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
                    self.log(L.t("✔ Tác vụ hoàn tất."), "ok")
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
            text = L.t("🟢") + f" {probe['name']}{tun}: " + L.t("đã kết nối")
            col = "#1a7f37"
        elif mode == "real":
            text = L.t("🔴 KHÔNG có SDR — chế độ bắt buộc thật sẽ BÁO LỖI")
            col = "#c62828"
        else:
            text = L.t("🟡 Tự động → MÔ PHỎNG (không thấy SDR)")
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
            messagebox.showerror(L.t("Thiếu mục tiêu"), L.t("Hãy nhập tên mục tiêu."))
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

    # ---- nơi lưu: chọn, áp dụng, phản ánh vào mọi module
    def _dir_value(self, key: str) -> str:
        import psr_paths as _p
        return _p.data_dir() if key == "data_dir" else _p.results_dir()

    def choose_dir(self, key: str, var) -> None:
        d = filedialog.askdirectory(title="Chọn thư mục", initialdir=var.get() or APP_DIR)
        if d:
            var.set(os.path.normpath(d))

    def apply_dirs(self) -> None:
        """Ghi nơi lưu mới vào settings.json và áp dụng NGAY cho mọi module."""
        import psr_paths as _p
        try:
            new_data = _p.set_data_dir(self.dir_vars["data_dir"].get())
            new_res = _p.set_results_dir(self.dir_vars["results_dir"].get())
        except Exception as exc:
            messagebox.showerror(L.t("Không đổi được thư mục"), str(exc))
            self.log(f"Lỗi đổi thư mục: {exc}", "err")
            return
        # áp dụng ngay trong tiến trình này
        globals()["DATA_DIR"] = new_data
        globals()["RESULTS_DIR"] = new_res
        psr_detect.RESULTS = new_res
        psr_detect.DATA = new_data
        record_unattended.DATA = new_data
        self.dir_vars["data_dir"].set(new_data)
        self.dir_vars["results_dir"].set(new_res)
        try:
            self._refresh_figure_list()
        except Exception:
            pass
        self.log(f"Đã áp dụng nơi lưu: dữ liệu → {new_data}", "ok")
        self.log(f"                        kết quả → {new_res}", "ok")

    def on_lang_change(self, _evt=None) -> None:
        """Đổi ngôn ngữ: lưu vào settings.json, hỏi khởi động lại để áp dụng."""
        name = self.lang_box.get()
        code = next((k for k, v in L.LANG_NAMES.items() if v == name), "vi")
        if code == L.current():
            return
        L.set_lang(code)
        vi = code == "vi"
        title = "Đổi ngôn ngữ" if vi else "Language changed"
        _nl = chr(10)
        msg = (("Đã lưu. Cần khởi động lại để áp dụng toàn bộ giao diện." + _nl
                + "Khởi động lại ngay?") if vi else
               ("Saved. A restart is required to apply it to the whole interface."
                + _nl + "Restart now?"))
        if messagebox.askyesno(title, msg):
            self.restart_app()

    def on_ui_scale_change(self, _evt=None) -> None:
        """Đổi độ phóng giao diện (100/115/130 %) — áp dụng sau khi khởi động lại."""
        try:
            txt = str(self.ui_scale_box.get()).replace("%", "").strip()
            val = float(txt) / 100.0
            if abs(val - theme.scale()) < 1e-6:
                return
            theme.set_scale(val)
        except Exception as e:                   # noqa: BLE001
            self.log(f"Không đổi được độ phóng: {e!r}", "err")
            return
        self.log(f"Độ phóng giao diện → {txt} % · khởi động lại để áp dụng…", "ok")
        self.root.after(200, self.restart_app)

    def restart_app(self) -> None:
        """Khởi động lại chính ứng dụng (giữ nguyên tham số dòng lệnh)."""
        import subprocess
        import sys as _sys
        try:
            if FROZEN:
                subprocess.Popen([_sys.executable] + _sys.argv[1:])
            else:
                subprocess.Popen([_sys.executable, os.path.abspath(__file__)]
                                 + _sys.argv[1:])
        except Exception as exc:                 # noqa: BLE001
            self.log(f"Không khởi động lại được: {exc}", "err")
            return
        try:
            self.root.destroy()
        except Exception:                        # noqa: BLE001
            pass

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
            messagebox.showerror(L.t("Lỗi"), L.t("Giờ/kênh/tsamp phải là số"))
            return
        source = self._source_key()
        probe = self.refresh_hw_status()
        if source == "real" and not probe["found"]:
            messagebox.showerror(
                L.t("Không có SDR"),
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
        self.run_bg(job, on_done=self._after_recorded)

    def stop_recording(self):
        self.stop_event.set()
        self.log(L.t("Yêu cầu DỪNG — chờ file đóng an toàn…"))

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
            self.log(L.t("Chưa có file .fil nào trong data/ — hãy ghi thử trước."), "err")
            return
        self.last_file = newest
        self.goto_detect(newest)

    def goto_detect(self, path: str | None = None) -> None:
        """Chuyển sang Tab 2 với ĐÚNG file vừa ghi VÀ DM tham chiếu của mục tiêu."""
        path = path or getattr(self, "last_file", None)
        if not path or not os.path.exists(path):
            self.log(L.t("Chưa có file vừa ghi để phân tích."), "err")
            return
        self.det_file.delete(0, "end")
        self.det_file.insert(0, path)
        dm = (self.rec_dm.get() or "").strip()
        if dm:
            self.det_dm.delete(0, "end")
            self.det_dm.insert(0, dm)
        name = os.path.basename(path)
        self.log(f"→ Tab 2: {name}" + (f" · DM tham chiếu {dm}" if dm else ""), "ok")
        try:
            self.nb.select(self.tab_det)
        except Exception:
            pass
        self.run_detect()

    def _after_recorded(self, meta=None) -> None:
        """Sau khi ghi xong: nhớ file, hiện nút chuyển tab, refresh danh sách hình."""
        p = (meta or {}).get("file") or (meta or {}).get("path")
        if p and os.path.exists(p):
            self.last_file = p
            try:
                self.btn_to_det.pack(side="left", padx=4)
            except Exception:
                pass
        self._refresh_figure_list()

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
        self.set_detect_step(3)          # đang phân tích
        try:                             # xoá kết quả M3 của lần chạy TRƯỚC
            self.m3_lbl.configure(text=L.t("… đang chạy"), style="Muted.TLabel")
        except (tk.TclError, AttributeError):
            pass
        path = self.det_file.get().strip()
        if not path or not os.path.exists(path):
            messagebox.showerror(L.t("Lỗi"), L.t("Chưa chọn file .fil hợp lệ"))
            return
        try:
            dm = float(self.det_dm.get()) if self.det_dm.get().strip() else None
            p = float(self.det_p.get()) if self.det_p.get().strip() else None
        except ValueError:
            messagebox.showerror(L.t("Lỗi"), L.t("DM/P phải là số"))
            return

        try:
            nchan_iq = int(self.det_iqn.get())
        except Exception:
            nchan_iq = 256

        self._last_metrics = None

        want_search = bool(getattr(self, "det_search", None)
                           and self.det_search.get())

        # khoá nút + đổi nhãn để chống bấm đúp gây 2 luồng cùng ghi kết quả;
        # luôn phục hồi trong finally kể cả khi luồng tính toán ném lỗi.
        _btn_txt = self.btn_det.cget("text")
        try:
            self.btn_det.configure(state="disabled",
                                   text=L.t("Đang chạy…"))
        except tk.TclError:
            pass

        def _restore():
            try:
                self.btn_det.configure(state="normal", text=_btn_txt)
            except tk.TclError:
                pass

        def job():
            try:
                self._last_metrics = psr_detect.detect(
                    path, dm_ref=dm, p_ref=p, nchan_iq=nchan_iq,
                    search_period=want_search)
            finally:
                self.post(_restore)      # chạy ở MAIN thread
        self.run_bg(job, on_done=self._after_detect)

    def _fill_guard(self, m: dict) -> None:
        """Hiển thị tóm tắt nhận dạng của ingest_guard cho lần chạy vừa rồi."""
        g = (m or {}).get("guard") or {}
        if not g:
            return
        fmt = ((g.get("steps") or {}).get("format") or {})
        kind = fmt.get("kind") or "?"
        stg = g.get("stage") or "?"
        inferred = bool(g.get("inferred")) or any(
            "anned" in str(x) for x in (g.get("warnings") or []) if "suy ra" in str(x))
        tags = ", ".join(g.get("tags") or []) or "—"
        met = g.get("metrics") or {}
        gate = (g.get("steps") or {}).get("gatekeeper") or {}
        adc = gate.get("adc") or {}
        sk = gate.get("sk") or {}
        rad = gate.get("radiometer") or {}
        ts = met.get("tsamp_s")
        branch = ("pulsar" if ts and ts <= 1e-3 else
                  "HI/continuum" if ts and ts > 10e-3 else "?")
        self.guard_lbl["fmt"].configure(
            text="{} ({})".format(kind, "INFERRED" if inferred else "EXACT"))
        self.guard_lbl["stage"].configure(text=str(stg))
        self.guard_lbl["dt"].configure(
            text=("{} µs → {}".format(round(ts * 1e6), branch) if ts else "—"))
        self.guard_lbl["bp"].configure(
            text=str(met.get("bandpass", "—")) + (
                " · flatten" if "flatten" in (g.get("actions") or []) else ""))
        self.guard_lbl["meta"].configure(
            text=("thiếu: " + ", ".join(g.get("inferred") or [])) if g.get("inferred")
            else "đầy đủ")
        self.guard_lbl["adc"].configure(
            text="{:.3f} % ({})".format(100.0 * float(adc.get("frac") or 0),
                                        adc.get("tag") or "n/a"))
        self.guard_lbl["sk"].configure(
            text="{} kênh ngoài ±3σ".format(sk.get("n_bad", 0))
            if sk.get("n_bad") is not None else "—")
        self.guard_lbl["rad"].configure(
            text=("{} ({:+.0%})".format(rad.get("tag"), rad.get("deviation") or 0)
                  if rad else "—"))
        self.guard_lbl["gap"].configure(
            text="{} gap".format(met.get("n_gaps", 0)))
        self.guard_lbl["tags"].configure(text=tags)
        # tóm tắt một dòng: nhãn dữ liệu + cảnh báo quan trọng nhất
        try:
            _warn = []
            if (adc.get("tag") or "").upper() not in ("", "OK", "N/A"):
                _warn.append("ADC " + str(adc.get("tag")))
            if str(rad.get("tag") or "") not in ("", "OK"):
                _warn.append(str(rad.get("tag")))
            if sk.get("n_bad"):
                _warn.append(f"{sk['n_bad']} kênh SK")
            _ok = not _warn
            self.guard_summary.configure(
                text=("✔ " if _ok else "⚠ ") + (tags if tags != "—" else
                                                L.t("bình thường"))
                + ("" if _ok else "  ·  " + " · ".join(_warn)),
                style="Ok.TLabel" if _ok else "Warn.TLabel")
        except tk.TclError:
            pass

    def open_result_file(self, name: str) -> None:
        """Mở một tệp trong thư mục kết quả của lần chạy gần nhất."""
        m = getattr(self, "_last_metrics", None) or {}
        d = m.get("out_dir")
        p = os.path.join(d, name) if d else ""
        if p and os.path.exists(p):
            try:
                os.startfile(p)          # noqa: S606 (Windows)
            except Exception:
                self.open_dir(os.path.dirname(p))
        else:
            self.log(f"Chưa có {name} — hãy chạy phát hiện trước.", "err")

    def _fill_m3(self, m: dict) -> None:
        """Hiển thị kết quả M3: P tốt nhất, SNR, số ứng viên Top-N."""
        ps = (m or {}).get("period_search") or {}
        if not ps:
            self.m3_lbl.configure(text=L.t("chưa chạy (cần P tham chiếu hoặc --search-period)"))
            return
        if not ps.get("searched"):
            self.m3_lbl.configure(text=L.t("lỗi: ") + str(ps.get("error"))[:60])
            return
        b = ps.get("best")
        n = len(ps.get("candidates") or [])
        if b:
            txt = "P = {:.3f} ms · SNR {:.1f}σ · Top-{} ({} sau sàng hài)".format(
                b["p_s"] * 1e3, b["snr"], n, ps.get("n_after_sift", n))
        else:
            txt = L.t("không có ứng viên vượt ngưỡng") + " ({} xét, {}σ)".format(
                n, ps.get("threshold", 8))
        self.m3_lbl.configure(text=txt, style="Ok.TLabel" if b else "Warn.TLabel")

    def _after_detect(self):
        self.set_detect_step(4)          # có kết quả
        try:
            self._fill_guard(getattr(self, "_last_metrics", None) or {})
        except Exception:
            pass
        try:
            self._fill_m3(getattr(self, "_last_metrics", None) or {})
        except Exception:
            pass
        self._refresh_figure_list()
        m = getattr(self, "_last_metrics", None) or {}
        stem = os.path.basename(str(m.get("out_dir") or "").rstrip("/" + chr(92)))
        if not stem:
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

    def open_figure_vector(self):
        """Mở bản VECTOR (SVG ưu tiên, rồi PDF) của hình đang chọn.

        SVG/PDF là vector: phóng to bao nhiêu cũng không vỡ nét, chữ chọn/copy
        được — dán thẳng vào báo cáo hay slide. Nếu lần chạy cũ chỉ có PNG thì
        báo rõ để chạy lại phát hiện (bản mới tự ghi kèm SVG/PDF).
        """
        name = self.det_figpick.get()
        if not name:
            messagebox.showinfo(L.t("Chưa có hình"), L.t("Hãy chạy phát hiện trước."))
            return
        stem = os.path.splitext(name)[0]
        for ext in (".svg", ".pdf"):
            p = os.path.join(RESULTS_DIR, stem + ext)
            if os.path.exists(p):
                try:
                    os.startfile(p)       # SVG → mở bằng trình duyệt/Inkscape
                    self.log(f"Đã mở bản vector: {os.path.basename(p)}", "ok")
                except OSError as e:
                    messagebox.showerror(L.t("Lỗi"), f"Không mở được {p}: {e}")
                return
        messagebox.showinfo(
            L.t("Chưa có bản vector"),
            L.t("Hình này chỉ có PNG (lần chạy cũ). Hãy bấm Chạy phát hiện lại "
                "để có kèm .svg/.pdf."))

    def open_figure_external(self):
        name = self.det_figpick.get()
        p = os.path.join(RESULTS_DIR, name) if name else None
        if p and os.path.exists(p):
            os.startfile(p)

    def _result_file(self, suffix):
        """Tệp trong thư mục kết quả của LẦN CHẠY gần nhất (results/<ngày>_<giờ>)."""
        m = getattr(self, "_last_metrics", None) or {}
        d = m.get("out_dir")
        if d:
            return os.path.join(d, suffix)
        stem = os.path.splitext(os.path.basename(self.det_file.get().strip()))[0]
        return os.path.join(RESULTS_DIR, stem, suffix)

    def open_report(self):
        p = self._result_file("detect_report.txt")
        if os.path.exists(p):
            os.startfile(p)
        else:
            self.log(f"Chưa có báo cáo: {p}", "err")

    def open_last_result_dir(self):
        m = getattr(self, "_last_metrics", None) or {}
        d = m.get("out_dir")
        if not (d and os.path.isdir(d)):
            d = RESULTS_DIR
        self.open_dir(d)

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
        self.run_bg(job, on_done=self._after_recorded)

    def run_stress(self):
        """Chạy toàn bộ corpus dữ liệu xấu (kể cả ca TIÊM vào nền RFI thật)."""
        def job():
            import stress_test
            stress_test.main()
        self.run_bg(job, on_done=self._after_recorded)

    def run_recorder_selftest(self):
        def job():
            import record_unattended as ru
            ok = ru.selftest()
            self.log(f"Recorder selftest: {'PASS' if ok else 'FAIL'}",
                     "ok" if ok else "err")
        self.run_bg(job)


# ---------------------------------------------------------------- selfcheck EXE
VERSION = "1.6.0"


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

    # ---- ĐA NGÔN NGỮ
    try:
        _bad = L.self_check()
        _cov = L.coverage()
        chk("đa ngôn ngữ (vi/en): dịch + fallback + settings.json", not _bad,
            f"{_cov['n_translated']} chuỗi đã dịch" + ("; " + "; ".join(_bad) if _bad else ""))
    except Exception as e:
        chk("đa ngôn ngữ (vi/en): dịch + fallback + settings.json", False, repr(e))

    # ---- CHÍNH SÁCH I/O: data/ chỉ đọc, sản phẩm vào results/<tên>
    try:
        import psr_paths as _paths
        _bad = _paths.self_check()
        chk("chính sách I/O (data/ chỉ đọc, results/ ghi được)", not _bad,
            "; ".join(_bad) or f"data={_paths.data_dir()}")
        _blocked = False
        try:
            _paths.assert_write_allowed(os.path.join(_paths.data_dir(), "zz.json"))
        except PermissionError:
            _blocked = True
        chk("chặn ghi vào thư mục dữ liệu thô", _blocked,
            _paths.data_dir())
        import psr_site as _st
        _prof = _st.ensure_default_profile()
        chk("hồ sơ trạm/kính tồn tại (configs/*.json)",
            os.path.exists(_prof), os.path.basename(_prof))
    except Exception as e:
        chk("chính sách I/O (data/ chỉ đọc, results/ ghi được)", False, repr(e))
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
                _m = psr_detect.detect(fil)
        finally:
            psr_detect.RESULTS = old
        outd = _m.get("out_dir", "")          # <ngày>_<giờ> do detect đặt
        need = ["fig1_overview.png", "fig2_detection.png",
                "detect_metrics.json", "detect_report.txt"]
        got = [f for f in need if os.path.exists(os.path.join(outd, f))]
        chk("phát hiện + xuất đủ 4 tệp", len(got) == 4, f"{len(got)}/4")
        # selfcheck chạy detect với RESULTS = tmp → sản phẩm phải nằm ngay dưới tmp
        chk("sản phẩm ra đúng MỘT thư mục con của RESULTS (không rải file)",
            os.path.dirname(os.path.abspath(outd)) == os.path.abspath(tmp),
            os.path.basename(outd))
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


def enable_dpi_awareness() -> tuple[float, bool]:
    """Cho Windows biết app tự vẽ theo DPI → chữ KHÔNG bị kéo giãn bitmap.

    Đây là nguyên nhân chính của “chữ mờ như độ phân giải thấp”: ở màn
    1366×768 đặt 125–150 %, tiến trình KHÔNG khai báo DPI-aware sẽ bị Windows
    phóng toàn bộ cửa sổ bằng nội suy (title bar vẫn nét vì Windows tự vẽ).

    Thử lần lượt 3 API (mỗi cái đều KIỂM CHỨNG lại bằng GetProcessDpiAwareness):
      1. SetProcessDpiAwarenessContext(PER_MONITOR_AWARE_V2) — Win 10 1703+
      2. SetProcessDpiAwareness(1)      — Win 8.1+
      3. SetProcessDPIAware()          — Win 7
    Trả về (tỉ lệ DPI/96, đã_aware).
    """
    scale, aware = 1.0, False
    if sys.platform != "win32":
        return scale, True
    try:
        import ctypes
        u32 = ctypes.windll.user32
        try:                       # 1) per-monitor v2
            u32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        except Exception:          # noqa: BLE001
            try:                   # 2) system aware
                ctypes.windll.shcore.SetProcessDpiAwareness(1)
            except Exception:      # noqa: BLE001
                try:               # 3) Win 7
                    u32.SetProcessDPIAware()
                except Exception:  # noqa: BLE001
                    pass
        try:                       # kiểm chứng thực sự đã aware hay chưa
            val = ctypes.c_int(0)
            ctypes.windll.shcore.GetProcessDpiAwareness(None, ctypes.byref(val))
            aware = val.value > 0
        except Exception:          # noqa: BLE001
            aware = True           # API cũ không có → coi như đã gọi thành công
        hdc = u32.GetDC(0)
        dpi = ctypes.windll.gdi32.GetDeviceCaps(hdc, 88)   # LOGPIXELSX
        u32.ReleaseDC(0, hdc)
        if dpi:
            scale = round(dpi / 96.0 * 2) / 2
    except Exception:              # noqa: BLE001
        pass
    return max(1.0, scale), aware


def main():
    if "--selfcheck" in sys.argv:
        sys.exit(selfcheck())
    dpi_scale, aware = enable_dpi_awareness()   # PHẢI trước khi tạo cửa sổ Tk
    if not aware:
        # Không khai báo được DPI → Windows sẽ kéo giãn bitmap (chữ nhoè).
        # Cảnh báo rõ thay vì im lặng cho người dùng tưởng app bị lỗi font.
        sys.stderr.write("[cảnh báo] không bật được DPI awareness — chữ có thể nhoè\n")
    try:                               # bảo đảm data/, results/, configs/ tồn tại
        import psr_paths as _p
        import psr_site as _s
        _p.ensure_dirs()
        _s.ensure_default_profile()
    except Exception:
        pass
    if "--lang" in sys.argv:
        try:
            code = sys.argv[sys.argv.index("--lang") + 1]
            L.set_lang(code)
        except Exception:
            pass
    root = tk.Tk()
    try:
        # CỐ ĐỊNH 96/72: 1 pt = 1,333 px. Phóng to giao diện do psr_theme.sp()
        # và cỡ chữ đảm nhiệm — nếu nhân thêm DPI ở đây thì mọi thứ bị phóng
        # 2 lần (chữ khổng lồ, cột bảng tràn ra ngoài cửa sổ).
        root.tk.call("tk", "scaling", 96.0 / 72.0)
    except tk.TclError:
        pass
    # Hệ số giao diện: mặc định theo DPI THẬT (như mọi app Windows), vẫn vẽ ở
    # pixel nguyên nên NÉT; người dùng đổi được 100/115/130 % trong Cài đặt.
    if not (os.environ.get("PSR_UI_SCALE")
            or (psr_paths.load_settings() or {}).get("ui_scale")):
        theme.set_scale(min(1.5, max(1.0, dpi_scale)), persist=False)
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()