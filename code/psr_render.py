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


def draw_panel(data: dict, fig, which: str = "a", pp=None):
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
    if _asp:
        try:                                  # giữ đúng tỉ lệ thiết kế của panel
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
