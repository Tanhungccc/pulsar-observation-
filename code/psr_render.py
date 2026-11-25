"""Vẽ lại các panel kết quả từ mảng đã cache trong lần detect.

Cửa sổ xem lớn dùng FigureCanvasTkAgg mới và toolbar Matplotlib gốc; module
này chỉ dựng lại nội dung panel, không tính lại detect hoặc DM.
"""
from __future__ import annotations

import numpy as np


def collect_render_data(*, s_dd, tsamp, pulses, pulses_ok, dm_grid, snr_dm,
                        dm_best, dm_ref, pulse_thresh, use_fold_scan,
                        fold_info, subband, header, path, met,
                        provenance="unknown (chưa xác minh)"):
    """Đóng gói các mảng cần cho 4 panel (KHÔNG bản sao lớn ngoài cần thiết)."""
    t_all = np.arange(len(s_dd)) * tsamp
    src = str(header.get("source") or "").strip()
    provenance = str(provenance or "unknown (chưa xác minh)")
    rawfile = str(header.get("rawdatafile") or "").lower()
    lowpath = str(path).lower().replace("\\", "/")
    if ("/data/stress/" in lowpath or "/selftest" in lowpath or "/extra/" in lowpath):
        provenance = "test/derived dataset"
    elif src.upper() in ("TEMP", "TEST", "UNKNOWN"):
        provenance = "unknown (header says TEMP/TEST)"
    elif any(k in rawfile for k in ("greenburst", "gbt", "zenodo")):
        provenance = "observational (header/source metadata)"
    return dict(
        series=np.asarray(s_dd - np.median(s_dd), dtype=np.float32),
        t_all_s=np.asarray(t_all, dtype=np.float64),
        pulses_ok=list(pulses_ok), pulses=list(pulses),
        dm_grid=np.asarray(dm_grid, float), snr_dm=np.asarray(snr_dm, float),
        dm_best=float(dm_best), dm_ref=dm_ref,
        pulse_thresh=float(pulse_thresh), use_fold_scan=bool(use_fold_scan),
        fold_info=fold_info, subband=subband, met=dict(met),
        source=src,
        provenance=str(provenance),
        telescope=str(header.get("telescope") or header.get("instrument") or ""),
        file=str(path))


PANELS = (
    ("a", "Chuỗi thời gian"),
    ("b", "Quét DM"),
    ("c", "Cận cảnh xung"),
    ("d", "Trễ dải con"),
)

# Tỉ lệ khung (rộng : cao) ĐÚNG NHƯ THIẾT KẾ của từng panel trong psr_plots.
# GUI dùng để khoá chiều cao khung xem — tránh kéo dãn hình theo cửa sổ.
PANEL_ASPECT = {
    "a": 7.2 / 2.6,
    "b": 7.2 / 3.6,
    "c": 7.2 / 3.0,
    "d": 7.2 / 3.0,
}


def draw_panel(data: dict, fig, which: str = "a", pp=None, resize_fig: bool = True):
    """Vẽ MỘT panel chiếm TOÀN BỘ khung — chữ đủ lớn, zoom mới có nghĩa.

    Vì sao: nhồi 4 panel vào dải ~230 px cao thì nhãn tiếng Việt đè nhau, người
    dùng không đọc được gì (đã thấy trên giao diện). Bài báo cũng bày từng hình
    riêng; ở đây cho chọn a/b/c/d, mỗi panel vẽ to đầy khung.
    """
    import psr_plots as _pp
    pp = pp or _pp
    fig.clear()
    ax = fig.add_subplot(111)
    _asp = PANEL_ASPECT.get(which)
    if resize_fig and _asp:
        try:                                  # giữ đúng tỉ lệ thiết kế khi xuất file
            fig.set_size_inches(9.0, round(9.0 / _asp, 2))
        except Exception:                     # noqa: BLE001
            pass
    s = data["series"].astype(float)
    t_all = data["t_all_s"]
    tsamp = float(t_all[1] - t_all[0]) if t_all.size > 1 else 1.0
    pulses_ok = data["pulses_ok"]

    if which == "a":
        pp.plot_timeseries(t_all, s, peaks=pulses_ok, ax=ax,
                           ylabel="cường độ tương đối (đã trừ nền, chuẩn hoá)",
                           title="(a) Chuỗi thời gian sau khử tán sắc", tag=False)
    elif which == "b":
        k = int(np.argmax(data["snr_dm"]))
        det = bool(float(data["snr_dm"][k]) >= data["pulse_thresh"])
        ttl = ("(b) Quét DM — fold tại P" if data["use_fold_scan"]
               else "(b) Quét DM — boxcar đa độ rộng")
        if not det:
            ttl += (f" — KHÔNG phát hiện (đỉnh {float(data['snr_dm'][k]):.1f}σ "
                    f"< {data['pulse_thresh']:.0f}σ)")
        pp.plot_dm_curve(data["dm_grid"], data["snr_dm"],
                         dm_meas=data["dm_best"] if det else None,
                         dm_true=data["dm_ref"],
                         ylabel=("SNR fold (σ)" if data["use_fold_scan"]
                                 else "SNR lọc khớp (σ)"),
                         ax=ax, title=ttl,
                         threshold=data["pulse_thresh"], tag=False)
    elif which == "c":
        if pulses_ok:
            p0 = pulses_ok[0]
            w_ms = p0.get("width_ms") or 1.0
            t0_ms = p0["t_s"] * 1e3
            hw = float(min(max(3.5 * w_ms, 3.0), 30.0))
            t_ms = t_all * 1e3
            sel = (t_ms >= t0_ms - hw) & (t_ms <= t0_ms + hw)
            if sel.sum() < 8:
                hw = max(hw, 3.0 * w_ms + 5.0)
                sel = (t_ms >= t0_ms - hw) & (t_ms <= t0_ms + hw)
            pk = [p for p in pulses_ok if abs(p["t_s"] * 1e3 - t0_ms) <= hw]
            pp.plot_pulse_profile(t_ms[sel], s[sel], pk[:3], data["met"], ax=ax,
                                  xlim_ms=(t0_ms - hw, t0_ms + hw),
                                  title=f"(c) Cận cảnh xung (±{hw:.1f} ms)",
                                  tag=False)
        elif data.get("fold_info") is not None and data["fold_info"]["snr"] > 8.0:
            pp.plot_fold_profile(data["fold_info"], ax=ax, tag=False,
                                 title="(c) Hồ sơ fold tại P tham chiếu")
        else:
            rej = [p for p in data["pulses"] if p.get("dm_consistent") is False]
            ttl = (f"(c) SNR theo thời gian — {len(rej)} ứng viên lệch DM"
                   if rej else "(c) SNR theo thời gian — không mẫu nào vượt ngưỡng")
            pp.plot_boxcar_snr(s, tsamp, threshold=data["pulse_thresh"], ax=ax,
                               candidates=rej or None, note="", title=ttl,
                               tag=False)
    elif which == "d":
        sb = data.get("subband")
        if sb:
            pp.plot_subband_lags(sb["freqs_mhz"], sb["lags_ms"], sb["dm"],
                                 sb["dm_err"], ax=ax, tag=False,
                                 title=f"(d) Trễ dải con — xung t = "
                                       f"{sb['t0_ms']:.1f} ms")
        elif data.get("fold_info") is not None:
            pp.plot_fold_snr_vs_dm(data["dm_grid"], data["snr_dm"],
                                   data["fold_info"], ax=ax, tag=False,
                                   threshold=data["pulse_thresh"],
                                   title="(d) SNR fold quanh DM tốt nhất")
        else:
            ax.text(0.5, 0.5, "không tìm thấy xung riêng lẻ để đo trễ dải con",
                    ha="center", va="center", fontsize=10, color="0.35",
                    transform=ax.transAxes)
            ax.set_xticks([]); ax.set_yticks([])
            ax.set_xlabel("tần số trung bình dải con (MHz)")
            ax.set_ylabel("trễ so với dải cao nhất (ms)")
            ax.set_title("(d) Trễ dải con — không áp dụng")
    try:
        fig.tight_layout()
    except Exception:                       # noqa: BLE001
        pass
    return ax


def draw_detection_panels(data: dict, fig, pp=None) -> None:
    """Vẽ 4 panel vào `fig` (Figure TkAgg của GUI) — vector thật, zoom sắc.

    Nội dung giống hệt fig2_detection.png: cùng hàm vẽ, cùng số liệu.
    """
    import psr_plots as _pp
    pp = pp or _pp
    if hasattr(fig, "clear"):
        fig.clear()
    ax = fig.subplots(2, 2)
    s = data["series"].astype(float)
    t_all = data["t_all_s"]
    pulses_ok = data["pulses_ok"]
    tsamp = float(t_all[1] - t_all[0]) if t_all.size > 1 else 1.0

    # ---------------- (a) chuỗi thời gian
    pp.plot_timeseries(t_all, s, peaks=pulses_ok, ax=ax[0, 0],
                       ylabel="cường độ tương đối (đã trừ nền, chuẩn hoá)",
                       title="(a) Chuỗi thời gian sau khử tán sắc")

    # ---------------- (b) quét DM
    title = ("(b) Quét DM — fold tại P" if data["use_fold_scan"]
             else "(b) Quét DM — boxcar đa độ rộng")
    k = int(np.argmax(data["snr_dm"]))
    if float(data["snr_dm"][k]) < data["pulse_thresh"]:
        title += (f" — KHÔNG phát hiện (đỉnh {float(data['snr_dm'][k]):.1f}σ "
                  f"< {data['pulse_thresh']:.0f}σ)")
    detected = bool(float(data["snr_dm"][k]) >= data["pulse_thresh"])
    pp.plot_dm_curve(data["dm_grid"], data["snr_dm"],
                     dm_meas=data["dm_best"] if detected else None,
                     dm_true=data["dm_ref"],
                     ylabel=("SNR fold (σ)" if data["use_fold_scan"]
                             else "SNR lọc khớp (σ)"),
                     ax=ax[0, 1], title=title,
                     threshold=data["pulse_thresh"])

    # ---------------- (c) cận cảnh xung
    met = data["met"]
    if pulses_ok:
        p0 = pulses_ok[0]
        w_ms = p0.get("width_ms") or 1.0
        t0_ms = p0["t_s"] * 1e3
        hw = float(min(max(3.5 * w_ms, 3.0), 30.0))
        t_ms = t_all * 1e3
        sel = (t_ms >= t0_ms - hw) & (t_ms <= t0_ms + hw)
        if sel.sum() < 8:
            hw = max(hw, 3.0 * w_ms + 5.0)
            sel = (t_ms >= t0_ms - hw) & (t_ms <= t0_ms + hw)
        pk_in = [p for p in pulses_ok if abs(p["t_s"] * 1e3 - t0_ms) <= hw]
        pp.plot_pulse_profile(t_ms[sel], s[sel], pk_in[:3], met, ax=ax[1, 0],
                              xlim_ms=(t0_ms - hw, t0_ms + hw),
                              title=f"(c) Cận cảnh xung (±{hw:.1f} ms)")
    elif data.get("fold_info") is not None and data["fold_info"]["snr"] > 8.0:
        pp.plot_fold_profile(data["fold_info"], ax=ax[1, 0],
                             title="(c) Hồ sơ fold tại P tham chiếu")
    else:
        rej = [p for p in data["pulses"] if p.get("dm_consistent") is False]
        ttl = (f"(c) SNR theo thời gian — {len(rej)} ứng viên lệch DM"
               if rej else "(c) SNR theo thời gian — không mẫu nào vượt ngưỡng")
        pp.plot_boxcar_snr(s, tsamp, threshold=data["pulse_thresh"],
                           ax=ax[1, 0], candidates=rej or None, note="",
                           title=ttl)

    # ---------------- (d) trễ dải con
    sb = data.get("subband")
    if sb:
        pp.plot_subband_lags(sb["freqs_mhz"], sb["lags_ms"], sb["dm"],
                             sb["dm_err"], ax=ax[1, 1],
                             title=f"(d) Trễ dải con — xung t = "
                                   f"{sb['t0_ms']:.1f} ms")
    elif data.get("fold_info") is not None:
        pp.plot_fold_snr_vs_dm(data["dm_grid"], data["snr_dm"],
                               data["fold_info"], ax=ax[1, 1],
                               threshold=data["pulse_thresh"],
                               title="(d) SNR fold quanh DM tốt nhất")
    else:
        a = ax[1, 1]
        a.text(0.5, 0.5, "không tìm thấy xung riêng lẻ để đo trễ dải con",
               ha="center", va="center", fontsize=9, color="0.35",
               transform=a.transAxes)
        a.set_xticks([]); a.set_yticks([])
        a.set_xlabel("tần số trung bình dải con (MHz)")
        a.set_ylabel("trễ so với dải cao nhất (ms)")
        a.set_title("(d) Trễ dải con — không áp dụng")

    src = data["source"]
    if src.lower() in ("", "temp", "unknown", "none", "test", "empty"):
        import os
        src = os.path.splitext(os.path.basename(data["file"]))[0]
    tel = data["telescope"].strip()
    _prov = data.get("provenance", "unknown (chưa xác minh)")
    fig.suptitle(f"Phát hiện pulsar — {src}"
                 + (f" ({tel})" if tel else "")
                 + (f" · {data.get('provenance')}"
                    if data.get("provenance") != "unknown (chưa xác minh)" else ""),
                 fontsize=11.5)
    try:
        fig.tight_layout(rect=(0, 0, 1, 0.965))
    except Exception:                       # noqa: BLE001
        pass
    if hasattr(pp, "finalize"):
        try:
            pp.finalize(fig)
        except Exception:                   # noqa: BLE001
            pass


def save_render_cache(data: dict, out_dir: str) -> None:
    """Lưu mảng vẽ vector gọn nhẹ (npz + json, không pickle) để mở lại vẫn zoom sắc."""
    import json
    import os
    npz_path = os.path.join(out_dir, "fig2_render.npz")
    meta_path = os.path.join(out_dir, "fig2_render.json")
    arrs = {
        "series": np.asarray(data["series"], dtype=np.float32),
        "t_all_s": np.asarray(data["t_all_s"], dtype=np.float64),
        "dm_grid": np.asarray(data["dm_grid"], dtype=np.float64),
        "snr_dm": np.asarray(data["snr_dm"], dtype=np.float64),
    }
    fi = data.get("fold_info")
    if fi is not None and "prof" in fi:
        arrs["fold_prof"] = np.asarray(fi["prof"], dtype=np.float64)
    sb = data.get("subband")
    if sb is not None:
        arrs["sb_freqs"] = np.asarray(sb["freqs_mhz"], dtype=np.float64)
        arrs["sb_lags"] = np.asarray(sb["lags_ms"], dtype=np.float64)
    np.savez_compressed(npz_path, **arrs)

    def _clean_pulses(plist):
        out = []
        for p in plist or []:
            out.append({k: (float(v) if isinstance(v, (int, float, np.floating, np.integer)) else v)
                        for k, v in p.items() if k in ("t_s", "snr", "width_ms", "width_samples", "dm_consistent", "dm_sub")})
        return out

    meta = {
        "pulses_ok": _clean_pulses(data.get("pulses_ok")),
        "pulses": _clean_pulses(data.get("pulses")),
        "dm_best": float(data["dm_best"]),
        "dm_ref": (float(data["dm_ref"]) if data.get("dm_ref") is not None else None),
        "pulse_thresh": float(data["pulse_thresh"]),
        "use_fold_scan": bool(data["use_fold_scan"]),
        "fold_meta": ({k: v for k, v in fi.items() if k != "prof"} if fi is not None else None),
        "subband_meta": ({k: float(v) for k, v in sb.items() if k not in ("freqs_mhz", "lags_ms")}
                         if sb is not None else None),
        "met": dict(data.get("met") or {}),
        "source": str(data.get("source") or ""),
        "provenance": str(data.get("provenance") or ""),
        "telescope": str(data.get("telescope") or ""),
        "file": str(data.get("file") or ""),
    }
    with open(meta_path, "w", encoding="utf-8") as fh:
        json.dump(meta, fh, ensure_ascii=False)


def load_render_cache(run_dir: str) -> dict | None:
    """Đọc lại cache vector từ thư mục kết quả (trả None nếu chạy cũ chưa có)."""
    import json
    import os
    npz_path = os.path.join(run_dir, "fig2_render.npz")
    meta_path = os.path.join(run_dir, "fig2_render.json")
    if not (os.path.exists(npz_path) and os.path.exists(meta_path)):
        return None
    try:
        with open(meta_path, encoding="utf-8") as fh:
            meta = json.load(fh)
        with np.load(npz_path, allow_pickle=False) as z:
            fi = None
            if meta.get("fold_meta") and "fold_prof" in z:
                fi = dict(meta["fold_meta"])
                fi["prof"] = np.array(z["fold_prof"])
            sb = None
            if meta.get("subband_meta") and "sb_freqs" in z and "sb_lags" in z:
                sb = dict(meta["subband_meta"])
                sb["freqs_mhz"] = np.array(z["sb_freqs"])
                sb["lags_ms"] = np.array(z["sb_lags"])
            return {
                "series": np.array(z["series"]),
                "t_all_s": np.array(z["t_all_s"]),
                "dm_grid": np.array(z["dm_grid"]),
                "snr_dm": np.array(z["snr_dm"]),
                "pulses_ok": meta.get("pulses_ok") or [],
                "pulses": meta.get("pulses") or [],
                "dm_best": float(meta["dm_best"]),
                "dm_ref": meta.get("dm_ref"),
                "pulse_thresh": float(meta["pulse_thresh"]),
                "use_fold_scan": bool(meta.get("use_fold_scan", False)),
                "fold_info": fi,
                "subband": sb,
                "met": meta.get("met") or {},
                "source": meta.get("source") or "",
                "provenance": meta.get("provenance") or "",
                "telescope": meta.get("telescope") or "",
                "file": meta.get("file") or "",
            }
    except Exception:                        # noqa: BLE001
        return None


class InteractivePlotController:
    """Điều khiển zoom/pan/kéo giãn trục kiểu Desmos & GeoGebra cho 1 graph.

    - Lăn chuột trên đồ thị: zoom quanh con trỏ (theo chế độ X+Y / X / Y, hoặc
      Shift = chỉ X, Ctrl = chỉ Y).
    - Lăn chuột / kéo trực tiếp trên vùng trục X (dưới trục) hoặc trục Y (trái
      trục): kéo giãn hoặc co riêng trục đó.
    - Kéo chuột trái trong vùng đồ thị: di chuyển (pan).
    - Tự khớp Y (auto_y=True): khi zoom/pan trục X, trục Y tự co giãn theo dữ
      liệu đang hiển thị trong [xmin, xmax].
    - Nháy đúp chuột trái hoặc phím R: về khung chuẩn ban đầu (1.0×).
    """

    def __init__(self, canvas, on_change=None, on_hover=None):
        self.canvas = canvas
        self.on_change = on_change
        self.on_hover = on_hover
        self.axis_mode = "xy"     # 'xy' | 'x' | 'y'
        self.auto_y = True
        self._home: tuple[tuple[float, float], tuple[float, float]] | None = None
        self._drag: dict | None = None
        self._xhair_v = None
        self._xhair_h = None
        self._snap_dot = None
        self._cids = [
            canvas.mpl_connect("scroll_event", self._on_scroll),
            canvas.mpl_connect("button_press_event", self._on_press),
            canvas.mpl_connect("motion_notify_event", self._on_motion),
            canvas.mpl_connect("button_release_event", self._on_release),
            canvas.mpl_connect("key_press_event", self._on_key),
            canvas.mpl_connect("figure_leave_event", self._on_leave),
        ]

    def _active_ax(self):
        axes = getattr(self.canvas.figure, "axes", None) or []
        return axes[0] if axes else None

    def _clear_crosshair(self) -> None:
        try:
            w = self.canvas.get_tk_widget()
            w.delete("_xhair")
        except Exception:                    # noqa: BLE001
            pass

    def _on_leave(self, _ev) -> None:
        self._clear_crosshair()
        if callable(self.on_hover):
            try:
                self.on_hover(None)
            except Exception:                # noqa: BLE001
                pass

    def _update_crosshair(self, ev, ax) -> None:
        if ev.xdata is None or ev.ydata is None or ax.images:
            self._clear_crosshair()
            if callable(self.on_hover):
                try:
                    self.on_hover(None)
                except Exception:            # noqa: BLE001
                    pass
            return
        qx, qy = float(ev.xdata), float(ev.ydata)
        sx, sy, snapped = qx, qy, False
        best_d2 = np.inf
        x0, x1 = sorted(ax.get_xlim())
        y0, y1 = sorted(ax.get_ylim())
        dx_span = max(x1 - x0, 1e-12)
        dy_span = max(y1 - y0, 1e-12)
        for ln in ax.get_lines():
            if not ln.get_visible():
                continue
            xd = np.asarray(ln.get_xdata(), float).ravel()
            yd = np.asarray(ln.get_ydata(), float).ravel()
            if xd.size < 2 or xd.size != yd.size:
                continue
            if xd.size == 2 and (np.isclose(xd[0], xd[1]) or np.isclose(yd[0], yd[1])):
                continue
            # Nhanh O(log N) nếu trục X tăng dần (chuỗi thời gian, DM curve)
            if xd.size > 32 and xd[0] < xd[-1] and xd[1] >= xd[0]:
                i_lo = max(0, int(np.searchsorted(xd, x0, side="left")))
                i_hi = min(xd.size, int(np.searchsorted(xd, x1, side="right")))
                if i_hi <= i_lo:
                    continue
                pos = int(np.searchsorted(xd[i_lo:i_hi], qx)) + i_lo
                cands = [k for k in (pos - 1, pos, pos + 1) if i_lo <= k < i_hi]
                if not cands:
                    continue
                for k in cands:
                    if not (np.isfinite(xd[k]) and np.isfinite(yd[k])):
                        continue
                    d2 = ((xd[k] - qx) / dx_span) ** 2 + ((yd[k] - qy) / dy_span) ** 2
                    if d2 < best_d2:
                        best_d2 = float(d2)
                        sx, sy = float(xd[k]), float(yd[k])
                        snapped = True
            else:
                vis = (xd >= x0) & (xd <= x1) & np.isfinite(xd) & np.isfinite(yd)
                if not vis.any():
                    continue
                xv, yv = xd[vis], yd[vis]
                d2 = ((xv - qx) / dx_span) ** 2 + ((yv - qy) / dy_span) ** 2
                idx = int(np.argmin(d2))
                if d2[idx] < best_d2:
                    best_d2 = float(d2[idx])
                    sx, sy = float(xv[idx]), float(yv[idx])
                    snapped = True

        # Vẽ crosshair trực tiếp trên tk.Canvas (0 ms, không redraw Matplotlib)
        try:
            w = self.canvas.get_tk_widget()
            w.delete("_xhair")
            fig_h = float(self.canvas.figure.bbox.height)
            bb = ax.bbox
            px, py_mpl = ax.transData.transform((sx, sy))
            py = fig_h - py_mpl
            bx0, bx1 = float(bb.x0), float(bb.x1)
            by0, by1 = fig_h - float(bb.y1), fig_h - float(bb.y0)
            w.create_line(px, by0, px, by1, fill="#2563EB", dash=(3, 3), width=1, tags="_xhair")
            w.create_line(bx0, py, bx1, py, fill="#2563EB", dash=(3, 3), width=1, tags="_xhair")
            if snapped:
                w.create_oval(px - 4, py - 4, px + 4, py + 4,
                              fill="#2563EB", outline="#FFFFFF", width=1.5, tags="_xhair")
        except Exception:                    # noqa: BLE001
            pass

        if callable(self.on_hover):
            try:
                self.on_hover((sx, sy, ax.get_xlabel(), ax.get_ylabel(), snapped))
            except Exception:                # noqa: BLE001
                pass

    def set_home(self) -> None:
        self._clear_crosshair()
        ax = self._active_ax()
        if ax is None:
            self._home = None
            return
        self._home = (tuple(float(v) for v in ax.get_xlim()),
                      tuple(float(v) for v in ax.get_ylim()))
        self._notify()

    def reset(self) -> None:
        self._clear_crosshair()
        ax = self._active_ax()
        if ax is None or self._home is None:
            return
        ax.set_xlim(*self._home[0])
        ax.set_ylim(*self._home[1])
        self.canvas.draw_idle()
        self._notify()

    def set_axis_mode(self, mode: str) -> None:
        if mode in ("xy", "x", "y"):
            self.axis_mode = mode

    def set_auto_y(self, enabled: bool) -> None:
        self.auto_y = bool(enabled)
        if self.auto_y:
            ax = self._active_ax()
            if ax is not None:
                self._autofit_y(ax)
                self.canvas.draw_idle()
                self._notify()

    def zoom_factors(self) -> tuple[float, float]:
        ax = self._active_ax()
        if ax is None or self._home is None:
            return (1.0, 1.0)
        hx0, hx1 = self._home[0]
        hy0, hy1 = self._home[1]
        cx0, cx1 = ax.get_xlim()
        cy0, cy1 = ax.get_ylim()
        zx = abs(hx1 - hx0) / max(abs(cx1 - cx0), 1e-12)
        zy = abs(hy1 - hy0) / max(abs(cy1 - cy0), 1e-12)
        return (zx, zy)

    def _notify(self) -> None:
        if callable(self.on_change):
            try:
                zx, zy = self.zoom_factors()
                self.on_change(zx, zy)
            except Exception:                # noqa: BLE001
                pass

    def _zone(self, ev, ax) -> str:
        """Phân vùng: 'plot' | 'x_axis' | 'y_axis' | 'none'."""
        bb = ax.bbox
        x, y = ev.x, ev.y
        if x is None or y is None:
            return "none"
        if bb.x0 <= x <= bb.x1 and bb.y0 <= y <= bb.y1:
            return "plot"
        if bb.x0 <= x <= bb.x1 and y < bb.y0 and y >= bb.y0 - 48:
            return "x_axis"
        if bb.y0 <= y <= bb.y1 and x < bb.x0 and x >= bb.x0 - 64:
            return "y_axis"
        return "none"

    def _autofit_y(self, ax) -> None:
        """Tự co giãn trục Y vừa khít phần dữ liệu nằm trong [xmin, xmax]."""
        x0, x1 = sorted(ax.get_xlim())
        ymins, ymaxs = [], []
        for ln in ax.get_lines():
            if not ln.get_visible():
                continue
            xd = np.asarray(ln.get_xdata(), float).ravel()
            yd = np.asarray(ln.get_ydata(), float).ravel()
            if xd.size == 0 or xd.size != yd.size:
                continue
            if xd.size == 2 and np.isclose(xd[0], xd[1]) and np.allclose(np.abs(yd), [0., 1.]):
                continue
            sel = (xd >= x0) & (xd <= x1) & np.isfinite(yd)
            if sel.any():
                ymins.append(float(np.min(yd[sel])))
                ymaxs.append(float(np.max(yd[sel])))
        if not ymins:
            return
        lo, hi = min(ymins), max(ymaxs)
        span = max(hi - lo, 1e-9)
        top_pad = 0.22 if ax.get_legend() is not None else 0.10
        ax.set_ylim(lo - 0.08 * span, hi + top_pad * span)

    def _on_scroll(self, ev) -> None:
        self._clear_crosshair()
        ax = self._active_ax()
        if ax is None:
            return
        zone = self._zone(ev, ax)
        if zone == "none":
            return
        step = getattr(ev, "step", 0) or (1 if getattr(ev, "button", "") == "up" else -1)
        scale = 0.84 if step > 0 else (1.0 / 0.84)

        key = str(getattr(ev, "key", "") or "").lower()
        if zone == "x_axis" or "shift" in key:
            do_x, do_y = True, False
        elif zone == "y_axis" or "control" in key or "ctrl" in key:
            do_x, do_y = False, True
        else:
            do_x = self.axis_mode in ("xy", "x")
            do_y = self.axis_mode in ("xy", "y")

        x0, x1 = ax.get_xlim()
        y0, y1 = ax.get_ylim()
        inv = ax.transData.inverted()
        dx_pt, dy_pt = inv.transform((ev.x, ev.y))
        cx = dx_pt if (ev.xdata is None) else ev.xdata
        cy = dy_pt if (ev.ydata is None) else ev.ydata

        if do_x:
            ax.set_xlim(cx - (cx - x0) * scale, cx + (x1 - cx) * scale)
        if do_y:
            ax.set_ylim(cy - (cy - y0) * scale, cy + (y1 - cy) * scale)
        elif do_x and self.auto_y and not ax.images:
            self._autofit_y(ax)

        self.canvas.draw_idle()
        self._notify()

    def _on_press(self, ev) -> None:
        self._clear_crosshair()
        ax = self._active_ax()
        if ax is None or ev.button != 1:
            return
        if getattr(ev, "dblclick", False):
            self.reset()
            return
        zone = self._zone(ev, ax)
        if zone == "none":
            return
        self._drag = {
            "zone": zone,
            "x_px": ev.x,
            "y_px": ev.y,
            "xlim": ax.get_xlim(),
            "ylim": ax.get_ylim(),
            "bb": ax.bbox,
        }

    def _on_motion(self, ev) -> None:
        ax = self._active_ax()
        if ax is None:
            return
        # Đổi hình con trỏ theo vùng (giống GeoGebra/Desmos)
        if self._drag is None:
            zone = self._zone(ev, ax)
            cur = {"x_axis": "sb_h_double_arrow",
                   "y_axis": "sb_v_double_arrow",
                   "plot": "crosshair"}.get(zone, "")
            try:
                self.canvas.get_tk_widget().configure(cursor=cur)
            except Exception:                # noqa: BLE001
                pass
            if zone == "plot":
                self._update_crosshair(ev, ax)
            else:
                self._clear_crosshair()
                if callable(self.on_hover):
                    try:
                        self.on_hover(None)
                    except Exception:        # noqa: BLE001
                        pass
            return
        if ev.x is None or ev.y is None:
            return
        d = self._drag
        z = d["zone"]
        dx_px = ev.x - d["x_px"]
        dy_px = ev.y - d["y_px"]
        x0, x1 = d["xlim"]
        y0, y1 = d["ylim"]
        bw = max(d["bb"].width, 1.0)
        bh = max(d["bb"].height, 1.0)

        if z == "x_axis":
            # Kéo sang phải = giãn trục X, kéo sang trái = nén trục X
            factor = float(np.exp(-dx_px / 140.0))
            cx = 0.5 * (x0 + x1)
            half = 0.5 * (x1 - x0) * factor
            ax.set_xlim(cx - half, cx + half)
            if self.auto_y and not ax.images:
                self._autofit_y(ax)
        elif z == "y_axis":
            # Kéo lên = giãn trục Y, kéo xuống = nén trục Y
            factor = float(np.exp(-dy_px / 120.0))
            cy = 0.5 * (y0 + y1)
            half = 0.5 * (y1 - y0) * factor
            ax.set_ylim(cy - half, cy + half)
        elif z == "plot":
            sx = (x1 - x0) / bw
            sy = (y1 - y0) / bh
            if self.axis_mode in ("xy", "x"):
                ax.set_xlim(x0 - dx_px * sx, x1 - dx_px * sx)
            if self.axis_mode in ("xy", "y"):
                ax.set_ylim(y0 - dy_px * sy, y1 - dy_px * sy)
            elif self.axis_mode == "x" and self.auto_y and not ax.images:
                self._autofit_y(ax)

        self.canvas.draw_idle()
        self._notify()

    def _on_release(self, _ev) -> None:
        self._drag = None

    def _on_key(self, ev) -> None:
        if str(getattr(ev, "key", "")).lower() == "r":
            self.reset()

