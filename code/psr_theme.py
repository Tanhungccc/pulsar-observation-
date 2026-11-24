# -*- coding: utf-8 -*-
"""psr_theme.py — Bộ quy chuẩn giao diện "Observatory Workspace".

Toàn bộ màu/khoảng cách/kiểu chữ nằm ở MỘT chỗ để mọi tab nhìn như một sản phẩm,
và để đổi giao diện không phải sờ vào code dựng widget.

Hai chế độ:
  · "dark"  (mặc định) — nền navy đậm, chữ sáng, nhấn xanh dương #2563EB.
    Nền tối giúp mắt đỡ mỏi khi ngồi đêm trong phòng lab, và ảnh phổ/dải động
    (vốn đã tối) hoà vào khung thay vì bị viền trắng chói.
  · "light" — nền xám sáng #F3F6FA, vùng nội dung trắng (dùng khi in, chiếu
    máy chiếu, hoặc làm việc ban ngày).

Nguyên tắc đã chốt với người dùng:
  · Cạnh VUÔNG, viền mảnh 1 px, phẳng — Tkinter không làm được bo góc thật nên
    không giả lập bằng ảnh (sẽ phình file và vỡ khi DPI khác).
  · Mỗi màn hình chỉ MỘT nút chính tô đặc (Primary). Nút Dừng là Stop (viền đỏ),
    chỉ bật đúng lúc. Còn lại là Ghost/Next.
  · Trạng thái luôn có BIỂU TƯỢNG + CHỮ, không truyền đạt chỉ bằng màu.
"""
from __future__ import annotations

import os
import sys

import tkinter as tk
from tkinter import ttk

FONT_UI = "Segoe UI"
FONT_MONO = "Consolas"
FONT_FALLBACK = ("Noto Sans", "DejaVu Sans", "TkDefaultFont")

# bước khoảng cách dùng chung (px) — nhân với hệ số phóng giao diện
S1, S2, S3 = 4, 8, 16

_scale = {"v": None}


def load_scale() -> float:
    """Hệ số phóng giao diện (1.0 = 100 %).

    Nguồn: PSR_UI_SCALE (env) > settings.json "ui_scale" > theo DPI thực.
    Vì sao cần: ở 1366×768 đặt 125–150 %, nếu để 100 % thì chữ nhỏ không đọc
    được; nếu để Windows tự kéo giãn thì chữ NHOÈ. Ta tự phóng font/padding
    theo đúng hệ số → nét ở độ phân giải thật.
    """
    cands = [os.environ.get("PSR_UI_SCALE")]
    mod = _settings_module()
    if mod is not None:
        try:
            cands.append(mod.load_settings().get("ui_scale"))
        except Exception:                        # noqa: BLE001
            pass
    for src in cands:
        try:
            v = float(str(src).strip().rstrip("x"))
            if 0.8 <= v <= 2.0:
                return v
        except Exception:                        # noqa: BLE001
            continue
    # MẶC ĐỊNH 1.0: KHÔNG phóng to. Độ nét đến từ việc vẽ đúng pixel
    # (DPI-aware + cỡ chữ nguyên px), không phải từ việc kéo to giao diện.
    return 1.0


def scale() -> float:
    if _scale["v"] is None:
        _scale["v"] = load_scale()
    return _scale["v"]


def sp(px: float) -> int:
    """Bước khoảng cách đã phóng (luôn ≥ 1 px)."""
    return max(1, int(round(float(px) * scale())))


def set_scale(v: float, persist: bool = True) -> float:
    v = round(min(2.0, max(0.8, float(v))) * 2) / 2
    _scale["v"] = v
    os.environ["PSR_UI_SCALE"] = f"{v:g}"
    if persist:
        mod = _settings_module()
        if mod is not None:
            try:
                d = mod.load_settings()
                d["ui_scale"] = v
                mod.save_settings(d)
            except Exception:                    # noqa: BLE001
                pass
    return v

PALETTES = {
    "dark": dict(
        mode="dark",
        bg="#0B1220",            # nền ứng dụng (navy, hơi "không gian")
        surface="#121C2E",       # thẻ nội dung
        surface2="#0E1728",      # ô nhập / hàng bảng xen kẽ
        header="#0A1526",        # thanh tiêu đề trên cùng
        header_ink="#E8F0FA",
        header_muted="#8FA6C4",
        primary="#2563EB",
        primary_hover="#1D4ED8",
        primary_ink="#FFFFFF",
        ink="#E6EDF7",
        muted="#93A4BD",
        line="#24334A",
        line2="#1B2740",
        ok="#34D399", ok_bg="#10291F", ok_line="#1F5B45",
        warn="#FBBF24", warn_bg="#2B2313", warn_line="#6B5320",
        err="#F87171", err_bg="#2B1618", err_line="#7A2C2F",
        info="#60A5FA", info_bg="#12233D", info_line="#2B4B78",
        log_bg="#080F1B", log_ink="#C7D3E4",
        sel_bg="#1B2E4D", sel_ink="#EAF1FB",
        table_head="#0E1728",
    ),
    "light": dict(
        mode="light",
        bg="#F3F6FA",
        surface="#FFFFFF",
        surface2="#FFFFFF",
        header="#10243D",
        header_ink="#E8EFF8",
        header_muted="#A9BDD6",
        primary="#2563EB",
        primary_hover="#1D4ED8",
        primary_ink="#FFFFFF",
        ink="#0F172A",
        muted="#5B6B82",
        line="#D8E1EC",
        line2="#E7EDF5",
        ok="#15803D", ok_bg="#E8F5EC", ok_line="#BEE0C8",
        warn="#B45309", warn_bg="#FDF3E3", warn_line="#EBD3A8",
        err="#B91C1C", err_bg="#FBEAEA", err_line="#F0C3C3",
        info="#1D4ED8", info_bg="#E8EEFD", info_line="#B9CBEE",
        log_bg="#0F172A", log_ink="#DCE6F3",
        sel_bg="#EEF4FF", sel_ink="#0F172A",
        table_head="#F7FAFD",
    ),
}
DEFAULT_MODE = "dark"
MODES = tuple(PALETTES)

_cache = {"mode": None, "font_ok": None}


# ------------------------------------------------------------------ cấu hình
def _settings_module():
    try:
        import psr_paths
        return psr_paths
    except Exception:                            # noqa: BLE001
        return None


def load_mode() -> str:
    """Thứ tự ưu tiên: biến môi trường PSR_THEME > settings.json > mặc định."""
    env = (os.environ.get("PSR_THEME") or "").strip().lower()
    if env in PALETTES:
        return env
    mod = _settings_module()
    if mod is not None:
        try:
            v = str(mod.load_settings().get("theme", "")).lower()
            if v in PALETTES:
                return v
        except Exception:                        # noqa: BLE001
            pass
    return DEFAULT_MODE


def set_mode(mode: str, persist: bool = True) -> str:
    mode = (mode or "").strip().lower()
    if mode not in PALETTES:
        raise ValueError(f"chế độ không hỗ trợ: {mode!r} (có {MODES})")
    _cache["mode"] = mode
    os.environ["PSR_THEME"] = mode
    if persist:
        mod = _settings_module()
        if mod is not None:
            try:
                d = mod.load_settings()
                d["theme"] = mode
                mod.save_settings(d)
            except Exception:                    # noqa: BLE001
                pass
    return mode


def mode() -> str:
    if _cache["mode"] not in PALETTES:
        _cache["mode"] = load_mode()
    return _cache["mode"]


def P() -> dict:
    """Bảng màu đang dùng."""
    return PALETTES[mode()]


def c(key: str) -> str:
    return P().get(key, "#000000")


def toggle() -> str:
    return "light" if mode() == "dark" else "dark"


# ------------------------------------------------------------------ kiểu chữ
def _pick_family(root=None) -> tuple[str, str]:
    """Trả về (font giao diện, font số). Ghép theo font có thật trên máy."""
    fams = set()
    try:
        import tkinter.font as tkfont
        fams = set(tkfont.families(root)) if root is not None else set()
    except Exception:                            # noqa: BLE001
        pass
    ui = FONT_UI if (not fams or FONT_UI in fams) else next(
        (f for f in FONT_FALLBACK if f in fams), "TkDefaultFont")
    mono = FONT_MONO if (not fams or FONT_MONO in fams) else "Courier New"
    return ui, mono


def fonts(root=None) -> dict:
    ui, mono = _pick_family(root)
    k = scale()

    def z(base_px, floor=9):
        """Cỡ chữ PIXEL NGUYÊN. Tk dùng số âm = pixel (số dương = point).

        Vì sao pixel chứ không point: 9 pt × scaling 1,333 = 12 px nhưng
        14 pt × 1,333 = 18,667 px → Tk vẽ glyph ở toạ độ lẻ → Windows nội suy
        → chữ “mờ mờ như độ phân giải thấp”. Pixel nguyên cho cạnh sắc.
        """
        return -max(floor, int(round(base_px * k)))

    return dict(
        ui=ui, mono=mono, scale=k,
        h1=(ui, z(20), "bold"),        # tiêu đề màn hình
        h2=(ui, z(12), "bold"),        # tiêu đề nhóm (UPPERCASE)
        body=(ui, z(14)),
        btn=(ui, z(14)),
        small=(ui, z(12)),
        num=(mono, z(14)),
        num_b=(mono, z(15), "bold"),
        tab=(ui, z(15)),
        log=(mono, z(14)),
    )


# ------------------------------------------------------------------ ttk style
def apply_styles(root: tk.Misc) -> dict:
    """Áp toàn bộ bảng màu lên ttk.Style. Gọi lại được khi đổi chế độ."""
    p = P()
    f = fonts(root)
    st = ttk.Style(root)
    # clam là theme DUY NHẤT cho phép đặt màu nền đầy đủ trên Windows
    # ("vista"/"winnative" bỏ qua background → chữ sáng trên nền sáng = không đọc được)
    try:
        st.theme_use("clam")
    except tk.TclError:
        pass

    st.configure(".", background=p["bg"], foreground=p["ink"],
                 fieldbackground=p["surface2"], bordercolor=p["line"],
                 focuscolor=p["primary"], font=f["body"])
    st.configure("TFrame", background=p["bg"])
    st.configure("Card.TFrame", background=p["surface"])
    st.configure("Header.TFrame", background=p["header"])
    st.configure("Line.TFrame", background=p["line"])

    st.configure("TLabel", background=p["bg"], foreground=p["ink"], font=f["body"])
    st.configure("Card.TLabel", background=p["surface"], foreground=p["ink"])
    st.configure("Muted.TLabel", background=p["bg"], foreground=p["muted"],
                 font=f["small"])
    st.configure("CardMuted.TLabel", background=p["surface"], foreground=p["muted"],
                 font=f["small"])
    st.configure("H1.TLabel", background=p["bg"], foreground=p["ink"], font=f["h1"])
    st.configure("CardH1.TLabel", background=p["surface"], foreground=p["ink"],
                 font=f["h1"])
    st.configure("H2.TLabel", background=p["bg"], foreground=p["muted"], font=f["h2"])
    st.configure("CardH2.TLabel", background=p["surface"], foreground=p["muted"],
                 font=f["h2"])
    st.configure("Ok.TLabel", background=p["surface"], foreground=p["ok"],
                 font=f["body"])
    st.configure("Warn.TLabel", background=p["surface"], foreground=p["warn"],
                 font=f["body"])
    st.configure("Err.TLabel", background=p["surface"], foreground=p["err"],
                 font=f["body"])
    st.configure("Num.TLabel", background=p["surface"], foreground=p["ink"],
                 font=f["num"])
    st.configure("HeaderBrand.TLabel", background=p["header"],
                 foreground=p["header_ink"], font=(f["ui"], 11, "bold"))
    st.configure("HeaderMeta.TLabel", background=p["header"],
                 foreground=p["header_muted"], font=(f["mono"], 8))

    # khung nhóm: thay LabelFrame bằng khung phẳng có đường kẻ trên
    st.configure("TLabelframe", background=p["surface"], bordercolor=p["line"],
                 relief="solid", borderwidth=1)
    st.configure("TLabelframe.Label", background=p["surface"],
                 foreground=p["muted"], font=f["h2"])

    # nút: 4 cấp thứ bậc. Phẳng thật: borderwidth=1, light/darkcolor TRÙNG nền
    # để clam không vẽ vệt sáng-tối 3D (đây là thứ làm nút trông “thô”).
    st.configure("TButton", background=p["surface2"], foreground=p["ink"],
                 bordercolor=p["line"], lightcolor=p["surface2"],
                 darkcolor=p["surface2"], font=f["btn"], padding=(sp(10), sp(5)),
                 relief="flat", borderwidth=1, focusthickness=1,
                 focuscolor=p["primary"], anchor="center")
    st.map("TButton",
           background=[("pressed", p["line"]), ("active", p["line2"]),
                       ("disabled", p["bg"])],
           foreground=[("disabled", p["muted"])],
           lightcolor=[("active", p["line2"]), ("pressed", p["line"])],
           darkcolor=[("active", p["line2"]), ("pressed", p["line"])],
           bordercolor=[("active", p["primary"])],
           relief=[("pressed", "flat")])
    st.configure("Primary.TButton", background=p["primary"],
                 foreground=p["primary_ink"], bordercolor=p["primary"],
                 lightcolor=p["primary"], darkcolor=p["primary"],
                 font=(f["ui"], f["btn"][1], "bold"),
                 padding=(sp(12), sp(6)), borderwidth=1)
    st.map("Primary.TButton",
           background=[("pressed", p["primary_hover"]),
                       ("active", p["primary_hover"]), ("disabled", p["line"])],
           lightcolor=[("pressed", p["primary_hover"]),
                       ("active", p["primary_hover"])],
           darkcolor=[("pressed", p["primary_hover"]),
                      ("active", p["primary_hover"])],
           foreground=[("disabled", p["muted"])],
           bordercolor=[("disabled", p["line"])])
    st.configure("Stop.TButton", background=p["err_bg"], foreground=p["err"],
                 bordercolor=p["err_line"], lightcolor=p["err_bg"],
                 darkcolor=p["err_bg"], font=(f["ui"], f["btn"][1], "bold"),
                 padding=(sp(12), sp(6)), borderwidth=1)
    st.map("Stop.TButton",
           background=[("active", p["err_bg"]), ("pressed", p["err_bg"]),
                       ("disabled", p["bg"])],
           foreground=[("disabled", p["muted"])],
           bordercolor=[("disabled", p["line"])])
    st.configure("Next.TButton", background=p["info_bg"], foreground=p["info"],
                 bordercolor=p["info_line"], lightcolor=p["info_bg"],
                 darkcolor=p["info_bg"], font=(f["ui"], f["btn"][1], "bold"),
                 padding=(sp(12), sp(6)), borderwidth=1)
    st.map("Next.TButton",
           background=[("active", p["info_bg"]), ("pressed", p["info_bg"]),
                       ("disabled", p["bg"])],
           foreground=[("disabled", p["muted"])])
    st.configure("NavSel.TButton", background=p["sel_bg"], foreground=p["primary"],
                 bordercolor=p["primary"], lightcolor=p["sel_bg"],
                 darkcolor=p["sel_bg"], font=(f["ui"], f["btn"][1], "bold"),
                 padding=(sp(10), sp(5)), borderwidth=1, anchor="w")
    st.map("NavSel.TButton", background=[("active", p["sel_bg"])],
           lightcolor=[("active", p["sel_bg"])],
           darkcolor=[("active", p["sel_bg"])])
    st.configure("Ghost.TButton", background=p["bg"], foreground=p["muted"],
                 bordercolor=p["line"], lightcolor=p["bg"], darkcolor=p["bg"],
                 font=f["btn"], padding=(sp(8), sp(4)), borderwidth=1,
                 anchor="w")
    st.map("Ghost.TButton", background=[("active", p["line2"])],
           lightcolor=[("active", p["line2"])], darkcolor=[("active", p["line2"])],
           foreground=[("active", p["ink"])])

    # tab: phẳng, gạch chân bằng màu chữ đậm + nền sáng hơn
    st.configure("TNotebook", background=p["bg"], bordercolor=p["line"],
                 tabmargins=(0, 0, 0, 0), borderwidth=0)
    st.configure("TNotebook.Tab", background=p["bg"], foreground=p["muted"],
                 font=f["tab"], padding=(sp(12), sp(6)), borderwidth=0)
    st.map("TNotebook.Tab",
           background=[("selected", p["surface"])],
           foreground=[("selected", p["primary"]), ("active", p["ink"])],
           expand=[("selected", (0, 0, 0, 0))])
    # Notebook ẩn tab (dùng cho điều hướng dọc ở tab Cài đặt)
    st.layout("Nav.TNotebook", [("Notebook.client", {"sticky": "nswe"})])
    # Dải tab do phần tử "TNotebook.Tab" vẽ — phải xoá layout CỦA NÓ, nếu chỉ
    # xoá ở layout Notebook thì tab vẫn hiện (đây là lý do bị "nhân bản" menu).
    st.layout("Nav.TNotebook.Tab", [])

    # bảng
    st.configure("Treeview", background=p["surface"], fieldbackground=p["surface"],
                 foreground=p["ink"], bordercolor=p["line"], borderwidth=1,
                 rowheight=sp(22), font=f["body"])
    st.map("Treeview", background=[("selected", p["sel_bg"])],
           foreground=[("selected", p["sel_ink"])])
    st.configure("Treeview.Heading", background=p["table_head"],
                 foreground=p["muted"], font=f["h2"], relief="flat",
                 padding=(sp(6), sp(5)))
    st.map("Treeview.Heading", background=[("active", p["line2"])])

    # ô nhập
    for w in ("TEntry", "TSpinbox", "TCombobox"):
        st.configure(w, fieldbackground=p["surface2"], foreground=p["ink"],
                     bordercolor=p["line"], insertcolor=p["ink"],
                     arrowcolor=p["muted"], padding=sp(4), font=f["body"])
        st.map(w, fieldbackground=[("readonly", p["surface2"]),
                                   ("disabled", p["bg"])],
               foreground=[("disabled", p["muted"])],
               bordercolor=[("focus", p["primary"])])
    # combobox thả xuống do Tk vẽ bằng listbox → phải set qua option database
    try:
        root.option_add("*TCombobox*Listbox.background", p["surface"])
        root.option_add("*TCombobox*Listbox.foreground", p["ink"])
        root.option_add("*TCombobox*Listbox.selectBackground", p["primary"])
        root.option_add("*TCombobox*Listbox.selectForeground", p["primary_ink"])
        root.option_add("*TCombobox*Listbox.font", f["body"])
    except Exception:                            # noqa: BLE001
        pass

    st.configure("TCheckbutton", background=p["bg"], foreground=p["ink"],
                 font=f["body"], focuscolor=p["primary"])
    st.map("TCheckbutton", background=[("active", p["bg"])],
           foreground=[("disabled", p["muted"])])
    st.configure("Card.TCheckbutton", background=p["surface"],
                 foreground=p["ink"], font=f["body"])
    st.map("Card.TCheckbutton", background=[("active", p["surface"])])

    st.configure("TScrollbar", background=p["line2"], troughcolor=p["bg"],
                 bordercolor=p["bg"], arrowcolor=p["muted"], borderwidth=0)
    st.map("TScrollbar", background=[("active", p["primary"])])
    st.configure("Vertical.TScrollbar", width=10)
    st.configure("Horizontal.TScrollbar", width=10)

    st.configure("TProgressbar", background=p["primary"],
                 troughcolor=p["surface2"], bordercolor=p["line"],
                 lightcolor=p["primary"], darkcolor=p["primary"])
    st.configure("TPanedwindow", background=p["bg"])
    st.configure("Sash", background=p["line"], borderwidth=0)
    st.configure("TSeparator", background=p["line"])
    # nút trên thanh tiêu đề (nền đậm): viền mảnh, chữ sáng
    st.configure("Header.TButton", background=p["header"],
                 foreground=p["header_ink"], bordercolor="#27405E",
                 lightcolor=p["header"], darkcolor=p["header"],
                 font=f["btn"], padding=(sp(8), sp(3)), borderwidth=1)
    st.map("Header.TButton",
           background=[("active", "#16283F"), ("pressed", "#16283F")],
           lightcolor=[("active", "#16283F")], darkcolor=[("active", "#16283F")],
           foreground=[("active", "#FFFFFF")])
    # con trỏ bàn tay trên nút (Tk mặc định để mũi tên → cảm giác “khô”)
    try:
        root.option_add("*TButton.cursor", "hand2")
        root.option_add("*TNotebook.Tab.cursor", "hand2")
    except Exception:                            # noqa: BLE001
        pass
    return dict(palette=p, fonts=f)


def paint_tk(widget, role: str = "bg") -> None:
    """Tô widget tk cổ điển (Text/Canvas/Frame thuần) theo bảng màu."""
    p = P()
    cfg = {
        "bg": dict(background=p["bg"], foreground=p["ink"]),
        "surface": dict(background=p["surface"], foreground=p["ink"]),
        "log": dict(background=p["log_bg"], foreground=p["log_ink"],
                    insertbackground=p["log_ink"],
                    selectbackground=p["primary"], selectforeground="#FFFFFF"),
        "header": dict(background=p["header"], foreground=p["header_ink"]),
    }.get(role, {})
    try:
        widget.configure(**cfg)
    except Exception:                            # noqa: BLE001
        pass


def chip_style(kind: str) -> dict:
    """Màu cho chip trạng thái: ok | warn | err | idle | run."""
    p = P()
    k = kind if kind in ("ok", "warn", "err", "idle", "run") else "idle"
    if k == "idle":
        return dict(background=p["surface2"], foreground=p["muted"],
                    bordercolor=p["line"])
    return dict(background=p[f"{k}_bg"], foreground=p[f"{k}"],
                bordercolor=p[f"{k}_line"] if f"{k}_line" in p else p["line"])


# trạng thái luôn kèm biểu tượng + chữ (không truyền đạt chỉ bằng màu)
ICON = {"ok": "✔", "warn": "⚠", "err": "✕", "idle": "○", "run": "⟳"}


def label_status(kind: str, text: str) -> str:
    return f"{ICON.get(kind, '•')} {text}"


def self_check() -> list[str]:
    """Kiểm tra bảng màu hợp lệ — dùng trong selftest/selfcheck."""
    bad = []
    for name, pal in PALETTES.items():
        for key, val in pal.items():
            if key == "mode":
                continue
            if not isinstance(val, str) or not val.startswith("#") or len(val) != 7:
                bad.append(f"{name}.{key} = {val!r}")
    need = ("bg", "surface", "header", "primary", "ink", "muted", "line",
            "ok", "warn", "err", "log_bg")
    for name, pal in PALETTES.items():
        for k in need:
            if k not in pal:
                bad.append(f"{name} thiếu khoá {k}")
    if load_mode() not in PALETTES:
        bad.append("chế độ mặc định không hợp lệ")
    if label_status("ok", "x").count("✔") != 1:
        bad.append("chip không có biểu tượng")
    return bad


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                            # noqa: BLE001
        pass
    issues = self_check()
    print("psr_theme self-check:", "OK" if not issues else issues)
    print("chế độ đang dùng:", mode())
    for k in ("bg", "surface", "header", "primary", "ok", "warn", "err"):
        print(f"  {k:8s} {c(k)}")
