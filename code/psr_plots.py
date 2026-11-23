# -*- coding: utf-8 -*-
"""
psr_plots.py — Vẽ biểu đồ CHUẨN cho kết quả quan sát pulsar.

Quy tắc bắt buộc (để không bao giờ sai ký hiệu / che dữ liệu):
    - mọi trục PHẢI có tên + đơn vị;
    - mọi giá trị in trên hình PHẢI lấy từ cùng dict metrics với file JSON;
    - chú giải mô tả đúng dòng đang vẽ (màu/ký hiệu khớp);
    - dấu thập phân dùng dấu chấm; nhãn tiếng Việt UTF-8;
    - **chú giải và chú thích KHÔNG được đè lên dữ liệu**: vị trí được chọn
      bằng cách đo hình học thật (bbox) sau khi vẽ, không đặt mù;
    - nhãn nguồn ("DỮ LIỆU THẬT / MÔ PHỎNG") nằm NGOÀI vùng vẽ, ở góc hình;
    - `figure_report()` trả về danh sách lỗi bố cục để test tự động kiểm tra.
"""
from __future__ import annotations

import re

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import AutoMinorLocator

plt.rcParams.update({
    "font.size": 9.5,
    "axes.titlesize": 10.5,
    "axes.labelsize": 9.5,
    "legend.fontsize": 8.5,
    "figure.dpi": 130,
    # PNG để xem nhanh (200 dpi đủ nét khi zoom vừa); SVG/PDF là VECTOR —
    # zoom bao nhiêu cũng không vỡ nét (chuẩn của bài báo: vector, không raster).
    "savefig.dpi": 200,
    "svg.fonttype": "none",     # giữ chữ là text thật → chọn/copy được, file nhỏ
    "pdf.fonttype": 42,         # TrueType nhúng → in ấn/hiệu đính được
    "axes.grid": True,
    "grid.alpha": 0.25,
    "xtick.minor.visible": True,
    "ytick.minor.visible": True,
    "font.family": "DejaVu Sans",
})

#: Định dạng vector ghi kèm mỗi hình. PNG = xem nhanh; SVG/PDF = zoom vô hạn.
VECTOR_FORMATS = ("svg", "pdf")


def save_all(fig, path_png: str, tries: int = 4) -> list:
    """Ghi 1 hình ra **PNG + SVG + PDF** cùng tên gốc, trả về đường dẫn đã ghi.

    Vì sao: PNG là ảnh raster — phóng to là thấy điểm ảnh. SVG/PDF là vector,
    zoom tới mức nào nét vẫn sắc, và mở được bằng trình duyệt (Edge/Chrome),
    Inkscape, Adobe Illustrator, Word/PowerPoint → dán thẳng vào báo cáo.
    """
    import os
    import time as _time
    stem = os.path.splitext(path_png)[0]
    out = []
    targets = [(path_png, None)] + [(f"{stem}.{ext}", ext) for ext in VECTOR_FORMATS]
    for target, ext in targets:
        for k in range(tries):
            try:
                if ext is None:
                    fig.savefig(target)
                else:
                    # dpi chỉ ảnh hưởng LỚP RASTER nhúng trong file vector
                    # (waterfall); chữ/trục vẫn là vector → vẫn nét vô hạn
                    fig.savefig(target, format=ext, dpi=150)
                out.append(target)
                break
            except OSError as e:
                if k == tries - 1:
                    raise OSError(f"không ghi được {target} sau {tries} lần: {e}"
                                  ) from e
                _time.sleep(0.4 * (k + 1))
    return out

C_PULSE = "#d62728"     # đỏ: tín hiệu pulsar

# ===================== QUY ƯỚC KÝ HIỆU TRÊN HÌNH (theo lối các bài báo) =====
#  Ý nghĩa                        | Ký hiệu / nét            | Hằng số
#  -------------------------------|--------------------------|---------------
#  Dữ liệu ĐO được                | chấm tròn đặc  ●         | MK_MEAS = "o"
#  Đỉnh xung ĐÃ PHÁT HIỆN         | tam giác ▽ ngay trên đỉnh| MK_PEAK = "v"
#  Giá trị DANH MỤC / lý thuyết   | đường nét đứt mảnh       | C_REF
#  Đường KHỚP                     | nét liền                 | C_FIT
#  Vùng xung W50                  | dải tô nhạt ±W50/2       | alpha 0.18
#  Bất định ±1σ                   | dải tô quanh đường khớp  | alpha 0.18
#
# Vì sao: trong hình học pulsar, người đọc quen "● = đo, -- = tham chiếu,
# — = khớp, dải tô = khoảng bất định"; KHÔNG dùng cột mốc + đường dọc cho mỗi
# đỉnh vì (a) che dữ liệu, (b) trùng với đường tham chiếu nét đứt, (c) khi có
# nhiều xung thì rối. Đỉnh chỉ cần một ▽ nhỏ nằm trên đỉnh, số liệu ghi ở
# chú giải.
MK_MEAS = "o"
MK_PEAK = "v"
C_REF = "#6b7280"        # xám đậm: giá trị danh mục / tham chiếu
C_NOISE = "#7f7f7f"     # xám: nền/nhiễu
C_FIT = "#1f77b4"       # xanh: đường khớp/đo
C_TRUE = "#2ca02c"      # xanh lá: giá trị tham chiếu (catalogue/mô phỏng)
C_RFI = "#ff7f0e"       # cam: RFI

_LEG_KW = dict(framealpha=1.0, facecolor="white", edgecolor="0.75",
               borderpad=0.4, labelspacing=0.3)
# Đơn vị hợp lệ → khoảng độ lớn hợp lý của dữ liệu trên trục đó.
# Dùng để phát hiện LỆCH BẬC (nhãn ghi ms nhưng dữ liệu là giây, v.v.).
UNIT_SCALE = {
    "ms": (1e-3, 1e8), "s": (1e-4, 1e6), "us": (1, 1e9), "µs": (1, 1e9),
    "MHz": (1e-1, 1e5), "kHz": (1, 1e8), "Hz": (1, 1e9),
    "pc cm-3": (1e-2, 1e5), "sigma": (1e-2, 1e6), "σ": (1e-2, 1e6),
    "pha": (0.0, 2.5), "dB": (-2e2, 2e2), "deg": (0.0, 180.0), "°": (0.0, 180.0),
    "%": (0.0, 100.0), "h": (1e-3, 1e4), "phut": (1e-2, 1e3), "min": (1e-2, 1e3),
}

_CORNERS = ("upper right", "upper left", "lower right", "lower left",
            "center right", "center left")


# --------------------------------------------------------------- hình học
def _data_display_points(ax) -> np.ndarray:
    """Toạ độ màn hình của mọi điểm dữ liệu thực (bỏ qua axvline/axhline)."""
    out = []
    for ln in ax.get_lines():
        if not ln.get_visible():
            continue
        x = np.asarray(ln.get_xdata(), float).ravel()
        y = np.asarray(ln.get_ydata(), float).ravel()
        if x.size == 0 or x.size != y.size:
            continue
        # axvline/axhline lưu [0, 1] theo trục chuẩn hoá — không phải dữ liệu
        if x.size == 2 and np.isclose(x[0], x[1]) and np.allclose(np.abs(y), [0., 1.]):
            continue
        n = min(x.size, 4000)
        idx = np.linspace(0, x.size - 1, n).astype(int)
        out.append(np.column_stack([x[idx], y[idx]]))
    # điểm đánh dấu (marker) rời
    for c in ax.collections:
        try:
            off = np.asarray(c.get_offsets(), float)
        except Exception:
            continue
        if off.size:
            out.append(off.reshape(-1, 2))
    if not out:
        return np.empty((0, 2))
    pts = np.vstack(out)
    pts = pts[np.isfinite(pts).all(axis=1)]
    if pts.size == 0:
        return np.empty((0, 2))
    return ax.transData.transform(pts)


def _count_inside(pts_disp: np.ndarray, bbox, pad: float = 2.0) -> int:
    if pts_disp.size == 0 or bbox is None:
        return 0
    x0, x1 = bbox.x0 - pad, bbox.x1 + pad
    y0, y1 = bbox.y0 - pad, bbox.y1 + pad
    return int(np.count_nonzero((pts_disp[:, 0] >= x0) & (pts_disp[:, 0] <= x1)
                                & (pts_disp[:, 1] >= y0) & (pts_disp[:, 1] <= y1)))


def _bbox_overlap_px(a, b) -> float:
    """Diện tích chồng lấn (px²) giữa hai bbox."""
    if a is None or b is None:
        return 0.0
    w = min(a.x1, b.x1) - max(a.x0, b.x0)
    h = min(a.y1, b.y1) - max(a.y0, b.y0)
    return max(0.0, w) * max(0.0, h)


def _norm_unit(u: str) -> str:
    """Chuẩn hoá tên đơn vị: bỏ $ { } , gộp khoảng trắng, đổi ký hiệu LaTeX."""
    t = (u or "").replace("$", "").replace("{", "").replace("}", "")
    t = t.replace("^{-3}", "-3").replace("^-3", "-3")
    t = t.replace(chr(92) + "sigma", "sigma").strip()
    return t


def _axis_unit(ax, which: str):
    """Đơn vị trong ngoặc cuối của nhãn trục (None nếu không có)."""
    lab = ax.get_xlabel() if which == "x" else ax.get_ylabel()
    if not lab:
        return None
    m = re.findall(r"[(]([^()]*)[)]\s*$", lab)
    return _norm_unit(m[-1]) if m else None


def _axis_magnitude(ax, which: str) -> float | None:
    """Độ lớn trung vị của dữ liệu trên trục (bỏ qua axvline/axhline)."""
    vals = []
    for ln in ax.get_lines():
        if not ln.get_visible():
            continue
        y = np.asarray(ln.get_ydata(), float).ravel()
        x = np.asarray(ln.get_xdata(), float).ravel()
        if x.size == 2 and np.isclose(x[0], x[1]) and np.allclose(np.abs(y), [0., 1.]):
            continue
        arr = x if which == "x" else y
        arr = arr[np.isfinite(arr)]
        if arr.size:
            vals.append(arr)
    if not vals:
        return None
    a = np.abs(np.concatenate(vals))
    a = a[a > 0]
    return float(np.median(a)) if a.size else None


_TITLE_NUM = re.compile(r"(?<![A-Za-z0-9.=±])([0-9]+[.,][0-9]+)")


def _title_units_missing(title: str) -> list:
    """Số có phần thập phân trong tiêu đề mà KHÔNG kèm đơn vị."""
    bad = []
    for m in _TITLE_NUM.finditer(title or ""):
        tail = (title[m.end():m.end() + 12] or "").strip()
        if re.match(r"^(ms|s|us|µs|MHz|kHz|Hz|pc|σ|sigma|°|%|h|phút|giây|dB)",
                    tail):
            continue
        bad.append(m.group(1))
    return bad


def _axes_bbox(ax):
    return ax.get_window_extent()


def _redraw(ax):
    fig = ax.figure
    try:
        fig.canvas.draw()
    except Exception:
        pass
    return fig


def place_legend(ax, kw=None):
    """Đặt chú giải trong dải trống phía trên trục — KHÔNG BAO GIỜ đè dữ liệu.

    Cách làm (đo bằng pixel thật, không đoán):
      1. dựng thử chú giải → đo chiều cao thật (px) → quy ra tỉ lệ `frac`;
      2. mở rộng ylim phía trên đúng `frac` để tạo dải trống;
      3. đặt chú giải vào dải đó (phải hoặc trái, chọn bên ít điểm hơn).
    Nhờ vậy chú giải không che dữ liệu và cũng không bị cắt ở mép hình.
    """
    handles, labels = ax.get_legend_handles_labels()
    if not handles:
        return None
    kw = dict(kw or {})
    _redraw(ax)
    ab = ax.get_window_extent()
    trial = ax.legend(handles=handles, labels=labels, loc="upper right",
                      **_LEG_KW, **kw)
    _redraw(ax)
    frac = (trial.get_window_extent().height + 10.0) / max(ab.height, 1.0)
    trial.remove()
    if frac > 0.42:                       # chú giải quá cao → thu nhỏ chữ
        kw.setdefault("fontsize", 7.2)
        trial = ax.legend(handles=handles, labels=labels, loc="upper right",
                          **_LEG_KW, **kw)
        _redraw(ax)
        frac = (trial.get_window_extent().height + 10.0) / max(ab.height, 1.0)
        trial.remove()
    frac = min(max(frac, 0.06), 0.55)

    if not getattr(ax, "_legend_space_reserved", False):
        y0, y1 = ax.get_ylim()
        # đỉnh dữ liệu THẬT (bỏ qua phần đã bị ylim cắt)
        ymax_data = y1
        cand = []
        for ln in ax.get_lines():
            yd = np.asarray(ln.get_ydata(), float).ravel()
            if yd.size == 0:
                continue
            if yd.size == 2 and np.allclose(np.abs(yd), [0., 1.]):
                continue                      # axvline/axhline (toạ độ trục)
            yd = yd[np.isfinite(yd)]
            yd = yd[yd <= y1 + 1e-9]
            if yd.size:
                cand.append(float(np.max(yd)))
        if cand:
            ymax_data = max(cand)
        if not np.isfinite(ymax_data) or ymax_data <= y0:
            ymax_data = y1
        band = min(frac + 0.02, 0.55)
        ax.set_ylim(y0, y0 + max(ymax_data - y0, (y1 - y0) * 0.25) / (1.0 - band))
        ax._legend_space_reserved = True
        ax._legend_band = band
    ax._legend_frac = getattr(ax, "_legend_band", frac + 0.02)

    _redraw(ax)
    pts = _data_display_points(ax)
    best_loc, best_n = "upper right", None
    for loc in ("upper right", "upper left", "lower right", "lower left"):
        # LƯU Ý: ax.legend() tự thay chú giải cũ; thử xong phải tạo lại chú giải
        # CUỐI CÙNG bằng ax.legend() (không dùng artist đã remove → sẽ mất hình).
        probe = ax.legend(handles=handles, labels=labels, loc=loc,
                          **_LEG_KW, **kw)
        _redraw(ax)
        n = _count_inside(pts, probe.get_window_extent())
        if best_n is None or n < best_n:
            best_loc, best_n = loc, n
        probe.remove()
    leg = ax.legend(handles=handles, labels=labels, loc=best_loc,
                    **_LEG_KW, **kw)
    ax._legend_outside = False
    # Đảm bảo KHOẢNG HỞ thật (px) giữa đáy chú giải và đỉnh dữ liệu ≥ 5 px;
    # nếu chưa đủ thì nới ylim phía trên rồi đặt lại (tối đa 4 lần).
    for _ in range(4):
        _redraw(ax)
        pts = _data_display_points(ax)
        legb = leg.get_window_extent()
        if pts.size == 0:
            break
        gap = legb.y0 - float(np.max(pts[:, 1]))
        n_in = _count_inside(pts, legb)
        if n_in == 0 and gap >= 5.0:
            break
        y0, y1 = ax.get_ylim()
        ax.set_ylim(y0, y1 + 0.07 * max(y1 - y0, 1e-12))
        ax._legend_space_reserved = True
        leg = ax.legend(handles=handles, labels=labels, loc=best_loc,
                        **_LEG_KW, **kw)
    ax._legend_n_points = _count_inside(pts, leg.get_window_extent()) if pts.size else 0
    _redraw(ax)
    return leg


def _tag(fig, text="DỮ LIỆU THẬT"):
    """Nhãn nguồn ở GÓC HÌNH (ngoài mọi vùng vẽ) — không bao giờ che dữ liệu."""
    t = fig.text(0.997, 0.004, text, ha="right", va="bottom", fontsize=7.5,
                 color="0.42",
                 bbox=dict(boxstyle="round,pad=0.28", fc="white", ec="0.78",
                           alpha=0.9, lw=0.6))
    t._is_tag = True
    return t


# --------------------------------------------------------------- kiểm tra
def figure_report(fig) -> list:
    """Liệt kê lỗi bố cục: chú giải đè dữ liệu, chữ tràn khỏi trục, chữ đè nhau."""
    problems = []
    _redraw(fig)
    for i, ax in enumerate(fig.axes):
        name = (ax.get_title() or f"axes{i}").split("—")[0].strip()[:40]
        pts = _data_display_points(ax)
        leg = ax.get_legend()
        abox = _axes_bbox(ax)
        leg_box = leg.get_window_extent() if leg is not None else None
        if leg is not None:
            n = _count_inside(pts, leg_box)
            if n > 0:
                problems.append(dict(panel=name, kind="legend_che_du_lieu",
                                     detail=f"chú giải phủ {n} điểm dữ liệu"))
        for t in ax.texts:
            if getattr(t, "_is_tag", False) or not t.get_text().strip():
                continue
            b = t.get_window_extent()
            if (b.x0 < abox.x0 - 1 or b.x1 > abox.x1 + 1
                    or b.y0 < abox.y0 - 1 or b.y1 > abox.y1 + 1):
                problems.append(dict(panel=name, kind="chu_tran_khoi_truc",
                                     detail=f'"{t.get_text()}" nằm ngoài khung'))
            if leg_box is not None and _bbox_overlap_px(b, leg_box) > 0:
                problems.append(dict(panel=name, kind="chu_de_len_chu_giai",
                                     detail=f'"{t.get_text()}" đè chú giải'))
            # chữ phủ lên ĐIỂM DỮ LIỆU (không tính đường axvline mảnh)
            n_pts = _count_inside(pts, b, pad=0.0)
            if n_pts > 0:
                problems.append(dict(panel=name, kind="chu_de_len_duong_ve",
                                     detail=f'"{t.get_text()}" phủ {n_pts} điểm dữ liệu'))
    # ĐƠN VỊ: mỗi trục phải có đơn vị trong ngoặc; độ lớn dữ liệu phải khớp
    for i, ax in enumerate(fig.axes):
        if getattr(ax, "get_label", lambda: "")() == "<colorbar>":
            continue                       # colorbar có nhãn riêng, bỏ qua
        name = (ax.get_title() or f"axes{i}").split("—")[0].strip()[:40]
        for which, axis_name in (("x", "trục x"), ("y", "trục y")):
            unit = _axis_unit(ax, which)
            if unit is None:
                lab = ax.get_xlabel() if which == "x" else ax.get_ylabel()
                problems.append(dict(panel=name, kind="nhan_thieu_don_vi",
                                     detail=f'{axis_name} "{lab}" thiếu đơn vị (..)'))
                continue
            rng = UNIT_SCALE.get(unit) or UNIT_SCALE.get(unit.lower())
            if not rng:
                continue                   # đơn vị lạ (ví dụ "đ.v. chuẩn hoá") → bỏ qua
            mag = _axis_magnitude(ax, which)
            if mag is None:
                continue
            lo, hi = rng
            if not (lo <= mag <= hi):
                problems.append(dict(
                    panel=name, kind="don_vi_lech_bac",
                    detail=(f'{axis_name} ghi "{unit}" nhưng |giá trị| ~ {mag:.3g} '
                            f'→ lệch bậc (kỳ vọng {lo:g}…{hi:g})')))
        miss = _title_units_missing(ax.get_title())
        if miss:
            problems.append(dict(panel=name, kind="tieu_de_thieu_don_vi",
                                 detail="số không đơn vị trong tiêu đề: "
                                        + ", ".join(miss[:3])))

    # tiêu đề: không tràn khỏi hình, không đè tiêu đề panel khác
    fbox = fig.bbox
    for i, ax in enumerate(fig.axes):
        tt = ax.title
        if not tt.get_text().strip():
            continue
        b = tt.get_window_extent()
        name_i = (tt.get_text() or f"axes{i}").split("—")[0].strip()[:40]
        if (b.x0 < fbox.x0 - 1 or b.x1 > fbox.x1 + 1
                or b.y1 > fbox.y1 + 1 or b.y0 < fbox.y0 - 1):
            problems.append(dict(panel=name_i, kind="tieu_de_tran_hinh",
                                 detail=f'"{tt.get_text()[:60]}…" tràn khỏi hình'))
        for j, other in enumerate(fig.axes):
            if other is ax or not other.title.get_text().strip():
                continue
            if _bbox_overlap_px(b, other.title.get_window_extent()) > 0:
                problems.append(dict(panel=name_i, kind="tieu_de_de_nhau",
                                     detail=f'"{tt.get_text()[:40]}…" đè tiêu đề panel khác'))
                break

    # nhãn nguồn phải nằm ngoài mọi vùng vẽ
    for t in fig.texts:
        if not getattr(t, "_is_tag", False):
            continue
        b = t.get_window_extent()
        for ax in fig.axes:
            if _bbox_overlap_px(b, _axes_bbox(ax)) > 0:
                problems.append(dict(panel="fig", kind="nhan_nguon_trong_truc",
                                     detail="nhãn nguồn chồng lên vùng vẽ"))
                break
    return problems


def finalize(fig, suptitle_pad: float = 1.0):
    """Căn bố cục, chừa chỗ cho chú giải ngoài trục, rồi trả về báo cáo lỗi."""
    fig.tight_layout()
    if any(getattr(ax, "_legend_outside", False) for ax in fig.axes):
        # chừa lề phải để chú giải ngoài không bị cắt
        for _ in range(6):
            issues = figure_report(fig)
            if any(p["kind"] == "legend_che_du_lieu" for p in issues):
                break
            rect = fig.subplotpars
            if rect.right <= 0.80:
                break
            fig.subplots_adjust(right=rect.right - 0.03)
    if suptitle_pad:
        fig.tight_layout(rect=(0, 0.012, 1, 0.972))
    fig.canvas.draw()
    return figure_report(fig)


# --------------------------------------------------------------- biểu đồ
def plot_waterfall(dyn, freqs_mhz, tsamp_s, ax=None, title="", db=True,
                   t_max_s=None, label_cbar="công suất tương đối", tag=True):
    """Waterfall tần số × thời gian. Đơn vị rõ ràng, không ngắt nhầm trục."""
    if ax is None:
        _, ax = plt.subplots(figsize=(7.2, 3.6))
    # GIẢM MẪU trước khi vẽ: imshow chỉ cần ~2000 cột; trước đây ép cả mảng
    # 150 triệu mẫu sang float64 (~1,2 GB) chỉ để vẽ một hình ~500 px.
    d = np.asarray(dyn)
    if d.ndim == 2:
        _nc, _nt = d.shape
        _st = max(1, _nt // 1400)
        _sc = max(1, _nc // 512)
        if _st > 1 or _sc > 1:
            d = d[::_sc, ::_st]
    d = np.asarray(d, dtype=np.float32)
    if t_max_s:
        d = d[:, : int(t_max_s / tsamp_s)]
    img = 10 * np.log10(np.maximum(d, 1e-12)) if db else d
    lo = np.percentile(img, 5); hi = np.percentile(img, 99.5)
    # rasterized=True: ảnh waterfall vốn là raster → nhúng 1 lớp ảnh vào SVG/PDF
    # thay vì vẽ hàng triệu hình chữ nhật (fig1.svg từ 4,5 MB → vài trăm kB,
    # mở tức thì) nhưng trục/chữ/nhãn VẪN là vector nên vẫn nét khi zoom.
    im = ax.imshow(img, aspect="auto", origin="lower", cmap="viridis",
                   rasterized=True,
                   vmin=lo, vmax=hi,
                   extent=[0.0, img.shape[1] * tsamp_s * 1e3,
                           freqs_mhz[0], freqs_mhz[-1]])
    cb = fig_cb = plt.colorbar(im, ax=ax, pad=0.02)
    cb.set_label(label_cbar + (" (dB)" if db else ""))
    ax.set_xlabel("thời gian kể từ đầu file (ms)")
    ax.set_ylabel("tần số (MHz)")
    ax.set_title(title)
    ax.yaxis.set_minor_locator(AutoMinorLocator(2))
    if tag:
        _tag(ax.figure)
    return ax


def plot_timeseries(t_s, series, peaks=None, ax=None, title="",
                    ylabel="công suất dư (đ.v. chuẩn hoá)", unit="ms",
                    tag=True):
    if ax is None:
        _, ax = plt.subplots(figsize=(7.2, 2.6))
    scale = 1e3 if unit == "ms" else 1.0
    t = np.asarray(t_s) * scale
    y = np.asarray(series, float)
    ax.plot(t, y, lw=0.7, color=C_NOISE, label="chuỗi thời gian")
    ymin, ymax = float(np.min(y)), float(np.max(y))
    span = max(ymax - ymin, 1e-9)
    if peaks:
        tp = np.array([p["t_s"] for p in peaks]) * scale
        sp = np.interp(np.array([p["t_s"] for p in peaks]), np.asarray(t_s), y)
        # cột mốc ngắn + tam giác đặt TRÊN đỉnh, CHỪA KHOẢNG HỞ nhỏ để không
        # chạm vào dữ liệu (tỉ lệ theo độ cao khung nên mọi cỡ hình đều thấy)
        gap = 0.05 * span
        stem = 0.10 * span
        ax.vlines(tp, sp + gap, sp + gap + stem, color=C_PULSE, lw=0.9, zorder=6)
        ax.plot(tp, sp + gap + stem, "v", color=C_PULSE, ms=8, mew=0.6, mec="k",
                zorder=7, label=f"xung phát hiện (n={len(peaks)})")
        ymax = max(ymax, float(np.max(sp + gap + stem)))
        if peaks:
            _p0 = peaks[0]
            ax.plot([], [], MK_PEAK, color=C_PULSE, ms=7, mew=0.6, mec="k",
                    label=(f"xung phát hiện: t = {_p0['t_s']*scale:.1f} "
                           f"{unit}, SNR = {_p0['snr']:.0f}"))
    ax.set_ylim(ymin - 0.08 * span, ymax + 0.10 * span)
    ax.set_xlabel(f"thời gian ({unit})")
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    place_legend(ax)
    if tag:
        _tag(ax.figure)
    return ax


def plot_dm_curve(dm_grid, snr, dm_meas=None, dm_true=None, dm_true_err=None,
                  ax=None, title="Quét DM — xung đơn",
                  ylabel="SNR lọc khớp (σ)", tag=True,
                  threshold=None):
    if ax is None:
        _, ax = plt.subplots(figsize=(7.2, 3.0))
    ax.plot(dm_grid, snr, ".-", ms=3.5, lw=1.0, color=C_FIT,
            label="SNR theo DM (đo)")
    x0, x1 = float(np.min(dm_grid)), float(np.max(dm_grid))
    ylo = float(np.min(snr))
    yhi = float(np.max(snr))
    # đường tham chiếu chỉ vẽ TRONG vùng dữ liệu (không chạy vào dải chú giải)
    y_lo = ylo - 0.08 * max(yhi - ylo, 1e-9)
    y_hi = yhi + 0.02 * max(yhi - ylo, 1e-9)
    if dm_true is not None and x0 <= dm_true <= x1:
        tol = dm_true_err if dm_true_err is not None else max(0.5, 0.01 * dm_true)
        ax.fill_betweenx([y_lo, y_hi], max(x0, dm_true - tol),
                         min(x1, dm_true + tol), color=C_TRUE, alpha=0.16,
                         lw=0, zorder=1)
        ax.plot([dm_true, dm_true], [y_lo, y_hi], ls="--", lw=1.3, color=C_TRUE,
                zorder=2, label=f"DM tham chiếu (catalogue) = {dm_true:.2f} "
                                f"± {tol:.2f} pc cm$^{{-3}}$")
    # chỉ vẽ đường ngưỡng khi nó NẰM TRONG khung nhìn (nếu không sẽ vô hình
    # nhưng vẫn hiện trong chú giải → gây hiểu nhầm)
    thr_visible = (threshold is not None and y_lo <= threshold <= yhi * 1.3)
    if thr_visible:
        ax.plot([x0, x1], [threshold, threshold], ls="-.", lw=1.0, color="0.45",
                zorder=2, label=f"ngưỡng phát hiện {threshold:.0f}σ")
    if dm_meas is not None:
        # marker TAM GIÁC ở đầu vạch = giá trị ĐO ĐƯỢC
        ax.plot([dm_meas, dm_meas], [y_hi, y_hi], MK_MEAS, color=C_PULSE, ms=6.5,
                mec="k", mew=0.5, zorder=4)
        ax.plot([dm_meas, dm_meas], [y_lo, y_hi], ls="-", lw=1.2, color=C_PULSE,
                zorder=3, label=f"DM đo được = {dm_meas:.2f} pc cm$^{{-3}}$")
    ax.set_xlim(x0 - 0.01 * (x1 - x0), x1 + 0.01 * (x1 - x0))
    ax.set_ylim(y_lo, max(yhi + 0.10 * max(yhi - ylo, 1e-9),
                          (threshold or 0.0) * 1.05 if thr_visible else yhi))
    ax.set_xlabel("DM (pc cm$^{-3}$)")
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    place_legend(ax)
    if tag:
        _tag(ax.figure)
    return ax


def plot_pulse_profile(t_ms, prof, peaks, metrics, ax=None,
                       title="Hồ sơ xung (đã khử tán sắc)", xlim_ms=None,
                       tag=True):
    """Hồ sơ xung với chú thích LẤY TỪ metrics — không bịa số, không tràn khung."""
    if ax is None:
        _, ax = plt.subplots(figsize=(7.2, 3.0))
    t = np.asarray(t_ms, float)
    y = np.asarray(prof, float)
    ax.plot(t, y, lw=1.1, color=C_FIT, label="chuỗi đã khử tán sắc")
    first = None
    # KHÔNG vẽ đường dọc cho từng xung: số liệu (t, SNR) nằm ở chú giải, còn
    # đỉnh được đánh dấu bằng ▽ ở khối "peaks" bên dưới → hình sạch, không
    # trùng với nét đứt dùng cho giá trị tham chiếu ở các panel khác.
    for i, p in enumerate(peaks):
        if i == 0:
            first = (p["t_s"] * 1e3, p)
    ymax = float(np.max(y))
    ymin = float(np.min(y))
    span = max(ymax - ymin, 1e-9)
    # PHẢI đặt xlim TRƯỚC khi đặt chú giải/chú thích: toạ độ chữ tính theo hệ
    # trục hiện hành, đổi xlim sau đó sẽ làm chữ trôi khỏi đúng chỗ.
    if xlim_ms:
        ax.set_xlim(*xlim_ms)
    ax.set_ylim(ymin - 0.10 * span, ymax + 0.22 * span)

    # Đánh dấu ĐỈNH XUNG bằng tam giác ngay trên đỉnh (số liệu đã ghi trong
    # chú giải) — không dùng hộp chú thích để khỏi che dữ liệu/đè chú giải.
    if first is not None:
        tp, p0 = first
        # đánh dấu NGAY tại thời điểm đo được (trùng đường nét đứt), không lệch
        # sang mẫu bên cạnh — tránh hiểu nhầm "xung ở chỗ khác"
        t_ap = float(tp)
        y_ap = float(np.interp(t_ap, t, y))
        # Chỉ MỘT dấu ▽ nằm ngay trên đỉnh, cách đỉnh một khoảng hở nhỏ:
        # không cột mốc, không đường dọc (cột mốc cũ vừa che dữ liệu vừa trùng
        # với nét đứt của giá trị tham chiếu nếu có).
        gap = 0.05 * span
        ax.plot([t_ap], [y_ap + gap], MK_PEAK, color=C_PULSE, ms=9,
                mew=0.0, zorder=7, label="_nolegend_")
        # Dải W50 (±W50/2 quanh đỉnh) — cách thể hiện bề rộng theo lối bài báo
        _w50 = metrics.get("w50_ms")
        if _w50:
            ax.axvspan(t_ap - _w50 / 2.0, t_ap + _w50 / 2.0,
                       color=C_REF, alpha=0.18, lw=0, zorder=1,
                       label=f"W50 = {_w50:.1f} ms")
        ax.set_ylim(ymin - 0.10 * span,
                    max(ymax + 0.22 * span, y_ap + gap + 0.16 * span))
    leg = place_legend(ax)
    if metrics.get("w50_ms"):
        ax.set_title(title + f" — W50 (hồ sơ) = {metrics['w50_ms']:.1f} ms")
    elif metrics.get("width_ms"):
        ax.set_title(title + f" — bộ lọc boxcar {metrics['width_ms']:.1f} ms")
    else:
        ax.set_title(title)
    ax.set_xlabel("thời gian (ms)")
    ax.set_ylabel("công suất dư (đ.v. chuẩn hoá)")
    if tag:
        _tag(ax.figure)
    return ax


def plot_subband_lags(f_mhz, lags_ms, dm_fit, dm_err, ax=None,
                      title="Trễ tán sắc giữa các dải con", tag=True):
    """lags_ms = trễ TƯƠNG ĐỐI dải tần số cao nhất (âm nếu đến sớm).
    Đường khớp: Δt(ν) = K·DM·(1/ν² − 1/ν_ref²), ν_ref = tần số cao nhất.
    """
    if ax is None:
        _, ax = plt.subplots(figsize=(7.2, 3.2))
    f = np.asarray(f_mhz, float)
    lags = np.asarray(lags_ms, float)
    ax.plot(f, lags, MK_MEAS, color=C_FIT, ms=5.5,
            label="trọng tâm xung đo được (dải con)")
    f_lo, f_hi = float(f.min()), float(f.max())
    xx = np.linspace(f_lo, f_hi, 200)
    K = 4.148808e3
    f_ref = float(np.max(f))
    yy = K * dm_fit * (1.0 / xx**2 - 1.0 / f_ref**2) * 1e3
    ax.plot(xx, yy, "-", color=C_PULSE, lw=1.4,
            label=f"khớp: DM = {dm_fit:.2f} ± {dm_err:.2f} pc cm$^{{-3}}$")
    if dm_err and dm_err > 0:            # dải ±1σ quanh đường khớp
        yy_lo = K * (dm_fit - dm_err) * (1.0 / xx**2 - 1.0 / f_ref**2) * 1e3
        yy_hi = K * (dm_fit + dm_err) * (1.0 / xx**2 - 1.0 / f_ref**2) * 1e3
        ax.fill_between(xx, yy_lo, yy_hi, color=C_PULSE, alpha=0.18, lw=0,
                        label="±1σ")
    ax.set_xlim(f_lo - 0.01 * (f_hi - f_lo), f_hi + 0.01 * (f_hi - f_lo))
    ax.margins(y=0.10)
    ax.set_xlabel("tần số trung bình dải con (MHz)")
    ax.set_ylabel("trễ so với dải cao nhất (ms)")
    ax.set_title(title)
    place_legend(ax)
    if tag:
        _tag(ax.figure)
    return ax


def plot_fold_profile(fold_info, ax=None, title="Hồ sơ fold", tag=True):
    """Hồ sơ tích luỹ theo pha (2 chu kỳ), ĐỈNH ĐƯỢC CĂN GIỮA.

    Xung trong dữ liệu fold thường vắt qua mốc pha 0 → nếu lấy argmax thẳng sẽ
    chỉ nhầm sang mép mảng (đã gặp: báo "pha 0.000" trong khi xung ở pha ~0.99).
    Cách làm: làm trơn VÒNG, tìm đỉnh, rồi quay vòng hồ sơ để đỉnh nằm giữa.
    """
    if ax is None:
        _, ax = plt.subplots(figsize=(7.2, 3.0))
    prof = np.asarray(fold_info["prof"], float)
    nb = int(fold_info.get("nbins", prof.size))
    p_s = float(fold_info["p_s"])
    snr = float(fold_info.get("snr", 0.0))
    cyc = float(fold_info.get("cycles", 0.0))
    med = float(np.median(prof))
    mad = 1.4826 * float(np.median(np.abs(prof - med))) + 1e-12
    y = (prof - med) / mad
    # làm trơn vòng (wrap) rồi tìm đỉnh → không bị lệch sang mép
    k = 5
    yw = np.concatenate([y[-k:], y, y[:k]])
    ys = np.convolve(yw, np.ones(2 * k + 1) / (2 * k + 1), mode="same")[k:-k]
    i_pk = int(np.argmax(ys))
    ph_pk_grid = i_pk / nb                 # pha trên LƯỚI GỐC
    # quay vòng để đỉnh nằm giữa khung (pha 0.5 và 1.5)
    y_roll = np.roll(y, nb // 2 - i_pk)
    ph = np.arange(nb) / nb
    ph2 = np.concatenate([ph, ph + 1.0])
    y2 = np.concatenate([y_roll, y_roll])
    ax.plot(ph2, y2, lw=1.0, color=C_FIT, label="hồ sơ tích luỹ")
    for kk in (0, 1):
        ax.axvline(0.5 + kk, color=C_PULSE, ls="--", lw=1.0, zorder=2,
                   label=("đỉnh xung" if kk == 0 else None))
    ymax = float(np.max(y2)); ymin = float(np.min(y2))
    span = max(ymax - ymin, 1e-9)
    ax.set_ylim(ymin - 0.10 * span, ymax + 0.26 * span)
    ax.set_xlim(0.0, 2.0)
    ax.set_xticks([0.0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0])
    ax.set_xlabel("pha (chu kỳ, đã căn đỉnh giữa)")
    ax.set_ylabel("tín hiệu (σ)")
    ax.set_title(f"{title} — P = {p_s*1e3:.3f} ms, {cyc:.0f} chu kỳ, "
                 f"SNR = {snr:.1f}")
    place_legend(ax)
    y0, y1 = ax.get_ylim()
    ax.text(1.0, y1 - 0.05 * (y1 - y0),      # giữa 2 xung: không đè đường nét đứt
            f"đỉnh ở pha lưới gốc {ph_pk_grid:.3f} · "
            f"t = {ph_pk_grid * p_s * 1e3:.2f} ms",
            ha="center", va="top", fontsize=7.8, color=C_PULSE,
            bbox=dict(boxstyle="round,pad=0.2", fc="white", ec=C_PULSE,
                      alpha=0.9, lw=0.6))
    if tag:
        _tag(ax.figure)
    return ax


def plot_fold_snr_vs_dm(dm_grid, snr, fold_info, ax=None,
                        title="SNR fold theo DM", tag=True, threshold=None):
    """Phóng to đường cong DM quanh giá trị tốt nhất (khi xung đơn không đủ)."""
    if ax is None:
        _, ax = plt.subplots(figsize=(7.2, 3.0))
    g = np.asarray(dm_grid, float)
    sv = np.asarray(snr, float)
    k = int(np.argmax(sv))
    half = max(8.0, 0.25 * g[k])
    sel = (g >= g[k] - half) & (g <= g[k] + half)
    ax.plot(g[sel], sv[sel], ".-", ms=4.0, lw=1.1, color=C_FIT,
            label="SNR khử tán sắc theo DM")
    if threshold is None or sv[k] >= threshold:
        ax.plot([g[k]], [sv[k]], "v", ms=8, mew=0.6, mec="k", color=C_PULSE,
                zorder=5, label=f"DM tốt nhất = {g[k]:.2f}")
    else:
        ax.plot([g[k]], [sv[k]], "o", ms=6, color="0.55", zorder=5,
                label=f"đỉnh nhiễu = {sv[k]:.1f}σ (dưới ngưỡng, KHÔNG phải xung)")
    if threshold is not None:
        ax.plot([g[sel][0], g[sel][-1]], [threshold, threshold], ls="-.",
                lw=1.0, color="0.45", zorder=2, label=f"ngưỡng {threshold:.0f}σ")
    ax.set_xlabel("DM (pc cm$^{-3}$)")
    ax.set_ylabel("SNR (σ)")
    ax.set_title(f"{title} — SNR = {fold_info['snr']:.1f}σ")
    place_legend(ax)
    if tag:
        _tag(ax.figure)
    return ax


def plot_boxcar_snr(series, tsamp_s, threshold=8.0, ax=None,
                    title="SNR lọc khớp theo thời gian", tag=True,
                    widths=(1, 2, 4, 8, 16, 32, 64),
                    candidates=None, note=""):
    """SNR(t) của lọc khớp boxcar (độ rộng tốt nhất) + đường ngưỡng.

    Dùng khi KHÔNG phát hiện xung: cho thấy rõ không mẫu nào vượt ngưỡng,
    thay vì lặp lại y nguyên chuỗi thời gian ở panel khác.
    """
    if ax is None:
        _, ax = plt.subplots(figsize=(7.2, 3.0))
    x = np.asarray(series, float)
    med = float(np.median(x))
    rms = 1.4826 * float(np.median(np.abs(x - med))) + 1e-12
    d = x - med
    c = np.concatenate(([0.0], np.cumsum(d)))
    best_z, best_w, best_series = -np.inf, 1, None
    for w in widths:
        if w > x.size:
            continue
        zs = (c[w:] - c[:-w]) / (rms * np.sqrt(w))
        if zs.size and float(np.max(zs)) > best_z:
            best_z, best_w = float(np.max(zs)), w
            best_series = np.concatenate([np.full(w - 1, np.nan), zs])
    if best_series is None:
        best_series = np.zeros(x.size)
    t = np.arange(best_series.size) * tsamp_s * 1e3
    ax.plot(t, best_series, lw=0.7, color=C_NOISE,
            label=f"SNR(t), boxcar {best_w} mẫu")
    ax.plot([t.min(), t.max()], [threshold, threshold], ls="-.", lw=1.2,
            color=C_PULSE, label=f"ngưỡng phát hiện {threshold:.0f}σ")
    zmax = max(float(np.nanmax(best_series)), threshold)
    ax.set_ylim(min(float(np.nanmin(best_series)) - 1.0, 0.0), zmax * 1.25)
    ax.set_xlabel("thời gian (ms)")
    ax.set_ylabel("SNR (σ)")
    # đánh dấu ỨNG VIÊN đã bị loại (nếu có) — để hình không nói sai sự thật
    if candidates:
        tc = np.array([c["t_s"] for c in candidates]) * 1e3
        sc = np.array([c["snr"] for c in candidates])
        ax.plot(tc, sc, "o", ms=7, mfc="none", mew=1.3, color=C_RFI, zorder=6,
                label=f"ứng viên bị loại (n={len(candidates)})")
    ax.set_title(f"{title} (cao nhất {best_z:.1f}σ){note}")
    place_legend(ax)
    if tag:
        _tag(ax.figure)
    return ax
