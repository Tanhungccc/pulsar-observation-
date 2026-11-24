"""Zoom / pan / thanh trượt cho hình matplotlib nhúng trong Tkinter.

Vì sao tự viết thay vì dùng Plotly/HTML: app phải là **Tkinter thuần** (không
webview, không trình duyệt, giữ nguyên bộ test và kích thước EXE). Plotly tạo
ra file HTML — người dùng không chấp nhận định dạng HTML, và mở HTML nghĩa là
phải có trình duyệt, không dùng được khi máy quan sát không có mạng/quyền.

Những gì lớp này làm được (giống cảm giác Plotly):
  · Lăn chuột  = zoom/quanh trục X tại đúng vị trí con trỏ (Shift = trục Y)
  · Kéo chuột trái trong khung = di chuyển (pan) cả 2 trục
  · Nháy đúp = trả về khung nhìn ban đầu
  · Thanh trượt "Vị trí" + "Độ rộng" bên dưới = cuộn/giãn cửa sổ dữ liệu
  · Phím ←/→/↑/↓ = cuộn, +/− = zoom, R = reset

Toàn bộ là vector khi lưu: nút Lưu của matplotlib ghi .svg → zoom vô hạn.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

DEFAULTS = dict(min_frac=0.002, max_frac=1.0, zoom_step=1.35, invert_y=True)


class ZoomPan:
    """Gắn hành vi zoom/pan vào một FigureCanvasTkAgg."""

    def __init__(self, canvas, fig, axes=None, scale: float = 1.0,
                 on_change=None):
        self.canvas = canvas
        self.fig = fig
        self.scale = max(0.5, float(scale))
        self.axes = list(axes) if axes is not None else [a for a in fig.axes]
        self.on_change = on_change
        self._home = {}
        self._drag = None
        self._cid = []
        self.active = self.axes[0] if self.axes else None
        self.refresh_home()
        self._bind()

    # ------------------------------------------------------------ tiện ích
    def _ensure_axes(self):
        """Hình mới tạo có thể chưa có axes → lấy lại từ figure khi cần."""
        if not self.axes and self.fig.axes:
            self.axes = list(self.fig.axes)
            if self.active not in self.axes:
                self.active = self.axes[0]
        return self.axes

    def refresh_home(self):
        """Ghi nhớ khung nhìn hiện tại làm mốc cho "reset"."""
        self._ensure_axes()
        self._home = {id(ax): (tuple(ax.get_xlim()), tuple(ax.get_ylim()))
                      for ax in self.axes}

    def _axes_at(self, event):
        ax = getattr(event, "inaxes", None)
        self._ensure_axes()
        if ax is not None and ax in self.axes:
            self.active = ax
            return ax
        return self.active if self.active in self.axes else (
            self.axes[0] if self.axes else None)

    def _notify(self):
        self.canvas.draw_idle()
        if self.on_change:
            try:
                self.on_change()
            except Exception:            # noqa: BLE001 — callback của UI
                pass

    # ------------------------------------------------------------- hành vi
    def zoom(self, ax, factor, centre=None, axis="x"):
        if ax is None:
            return
        if axis in ("x", "both"):
            lo, hi = ax.get_xlim()
            c = (lo + hi) / 2.0 if centre is None else float(centre)
            half = max((hi - lo) / 2.0 / factor, 1e-12)
            ax.set_xlim(c - half, c + half)
        if axis in ("y", "both"):
            lo, hi = ax.get_ylim()
            c = (lo + hi) / 2.0 if centre is None else float(centre)
            half = max((hi - lo) / 2.0 / factor, 1e-12)
            ax.set_ylim(c - half, c + half)
        self._notify()

    def pan(self, ax, dx_px, dy_px):
        if ax is None:
            return
        bb = ax.bbox
        if bb.width > 1:
            lo, hi = ax.get_xlim()
            d = (hi - lo) * dx_px / bb.width
            ax.set_xlim(lo - d, hi - d)
        if bb.height > 1:
            lo, hi = ax.get_ylim()
            d = (hi - lo) * dy_px / bb.height
            ax.set_ylim(lo - d, hi - d)
        self._notify()

    def reset(self, ax=None):
        for a in ([ax] if ax is not None else self.axes):
            home = self._home.get(id(a))
            if home:
                a.set_xlim(*home[0])
                a.set_ylim(*home[1])
        self._notify()

    def window(self, ax=None):
        """(lo, hi) hiện tại của trục X → dùng cho thanh trượt."""
        self._ensure_axes()
        a = ax or self.active
        return a.get_xlim() if a is not None else (0.0, 1.0)

    def set_window(self, lo, width, ax=None):
        a = ax or self.active
        if a is None:
            return
        home = self._home.get(id(a))
        if not home:
            return
        hx0, hx1 = home[0]
        w = max((hx1 - hx0) * float(width), 1e-12)
        x0 = hx0 + (hx1 - hx0) * float(lo)
        a.set_xlim(x0, x0 + w)
        self._notify()

    # ------------------------------------------------------------- sự kiện
    def _bind(self):
        c = self.canvas
        self._cid = [c.mpl_connect("scroll_event", self.on_scroll),
                     c.mpl_connect("button_press_event", self.on_press),
                     c.mpl_connect("motion_notify_event", self.on_motion),
                     c.mpl_connect("button_release_event", self.on_release),
                     c.mpl_connect("key_press_event", self.on_key)]

    def detach(self):
        for cid in self._cid:
            try:
                self.canvas.mpl_disconnect(cid)
            except Exception:            # noqa: BLE001
                pass
        self._cid = []

    def on_scroll(self, event):
        ax = self._axes_at(event)
        axis = "y" if (getattr(event, "key", None) == "shift") else "x"
        centre = getattr(event, "ydata", None) if axis == "y" else getattr(
            event, "xdata", None)
        self.zoom(ax, 1.0 / DEFAULTS["zoom_step"] if event.button == "down"
                  else DEFAULTS["zoom_step"], centre, axis)
        if self.on_change:
            self.on_change()

    def on_press(self, event):
        ax = self._axes_at(event)
        if getattr(event, "dblclick", False):
            self.reset(ax)
            self._drag = None
            return
        if ax is not None and event.button in (1, 2):
            self._drag = (ax, event.x, event.y)

    def on_motion(self, event):
        if not self._drag:
            return
        ax, x0, y0 = self._drag
        self.pan(ax, event.x - x0, event.y - y0)
        self._drag = (ax, event.x, event.y)

    def on_release(self, _event):
        self._drag = None

    def on_key(self, event):
        ax = self.active
        k = getattr(event, "key", "")
        if k in ("r", "R"):
            self.reset(ax)
        elif k in ("+", "="):
            self.zoom(ax, DEFAULTS["zoom_step"], None, "both")
        elif k in ("-", "_"):
            self.zoom(ax, 1.0 / DEFAULTS["zoom_step"], None, "both")
        elif k in ("left", "right", "up", "down"):
            d = 0.1
            dx = {"left": -d, "right": d}.get(k, 0.0)
            dy = {"up": d, "down": -d}.get(k, 0.0)
            lo, hi = self.window(ax)
            if dx:
                w = hi - lo
                ax.set_xlim(lo + dx * w, hi + dx * w)
            if dy:
                lo, hi = ax.get_ylim()
                w = hi - lo
                ax.set_ylim(lo + dy * w, hi + dy * w)
            self._notify()


def add_sliders(parent, zp, *, label_pos="Vị trí cửa sổ",
                label_zoom="Độ rộng", rows=1):
    """Thanh trượt Tk: cuộn + giãn cửa sổ dữ liệu của trục X đang chọn.

    Trả về Frame chứa 2 thanh trượt; giá trị 0…1 tính theo khung nhìn ban đầu.
    """
    box = ttk.Frame(parent)
    state = {"pos": 0.0, "width": 1.0, "busy": False}

    s_pos = ttk.Scale(box, from_=0.0, to=1.0, orient="horizontal")
    s_zoom = ttk.Scale(box, from_=0.02, to=1.0, orient="horizontal")
    s_zoom.set(1.0)

    def apply(_evt=None):
        if state["busy"]:
            return
        state["busy"] = True
        try:
            zp.set_window(s_pos.get(), s_zoom.get())
        finally:
            state["busy"] = False

    def sync_from_view(_evt=None):
        """Khi zoom/pan bằng chuột → cập nhật lại 2 thanh trượt."""
        if state["busy"]:
            return
        home = zp._home.get(id(zp.active))
        if not home:
            return
        hx0, hx1 = home[0]
        lo, hi = zp.window()
        span = max(hx1 - hx0, 1e-12)
        state["busy"] = True
        try:
            s_zoom.set(max(0.02, min(1.0, (hi - lo) / span)))
            s_pos.set(max(0.0, min(1.0, (lo - hx0) / span)))
        finally:
            state["busy"] = False

    s_pos.configure(command=apply)
    s_zoom.configure(command=apply)
    ttk.Label(box, text=label_pos, style="Muted.TLabel").grid(
        row=0, column=0, sticky="w", padx=(0, 6))
    s_pos.grid(row=0, column=1, sticky="ew", pady=1)
    ttk.Label(box, text=label_zoom, style="Muted.TLabel").grid(
        row=1, column=0, sticky="w", padx=(0, 6))
    s_zoom.grid(row=1, column=1, sticky="ew", pady=1)
    box.columnconfigure(1, weight=1)
    _prev = zp.on_change
    zp.on_change = (lambda: (sync_from_view(), _prev() if _prev else None))
    return box
