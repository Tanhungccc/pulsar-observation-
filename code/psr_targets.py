# -*- coding: utf-8 -*-
"""
psr_targets.py — Danh mục mục tiêu + khả năng quan sát từ TP.HCM + S/N dự đoán.

Chạy:
    python psr_targets.py                # bảng pulsar cho từng cấu hình
    python psr_targets.py --csv          # ghi results/targets.csv

Ghi chú: thông lượng S là GIÁ TRỊ XẤP XỈ theo bậc (tra ATNF để lấy số chính xác;
cột S trong bảng in kèm "~"). Mọi kết luận "khả thi/không" đều nhạy với S và Tsys
→ hãy cập nhật bảng rồi chạy lại, đừng trích số trong tài liệu như số chốt.
"""
from __future__ import annotations

import argparse
import csv
import math
import os
from datetime import datetime, timedelta, timezone

import numpy as np

from psr_core import ensure_utf8_stdout
from psr_sensitivity import (Config, Dish, chan_smear_ms, required_time_s,
                             snr_fold, verdict)

# Vị trí trạm lấy từ HỒ SƠ (psr_site) — không còn viết cứng TP.HCM.
# Đổi hồ sơ: đặt biến môi trường PSR_PROFILE=<đường dẫn json>.
import psr_site as _site                      # noqa: E402
LAT_DEG = _site.LAT_DEG
LON_DEG = _site.LON_DEG
TZ_H = _site.TZ_H
RESULTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "results")

# ------------------------------------------------------------------- danh mục
# NGUỒN SỐ: ATNF Pulsar Catalogue v2.9.0 (psrcat.db, tải 2026-11).
#   s408  = S400  (mJy), s1400 = S1400 (mJy), w1400 = W50 đo ở 1.4 GHz (ms).
#   w408 KHÔNG lấy từ catalogue (catalogue không có W50 ở 400 MHz) mà TÍNH
#   bằng mô hình ở dưới: giãn nội tại W ∝ ν^-0.3 + tán xạ τ ∝ DM^2.2 ν^-4.4.
# LƯU Ý BẮT BUỘC: trước 2026-11 danh mục này dùng số GẦN ĐÚNG, sai tới ×7
#   (B0329+54 ghi 200 mJy thay vì 1500; Vela ghi 700 thay vì 5000) → mọi bảng
#   SNR cũ đều sai. Đã đối chiếu lại toàn bộ với psrcat.db.
import math as _math


def tau_scattering_ms(dm: float, f_mhz: float) -> float:
    """Thời gian tán xạ (ms) theo Bhat+2004: τ(1 GHz) ≈ 1.3e-4·(DM/100)^2.2 s,
    quy đổi τ ∝ ν^-4.4. Dùng để biết xung có bị nhòe ở tần số thấp hay không."""
    return 1.3e-4 * (max(dm, 0.0) / 100.0) ** 2.2 * (f_mhz / 1000.0) ** -4.4 * 1e3


def w50_at(w50_1400_ms: float, dm: float, f_mhz: float,
           alpha_w: float = 0.3) -> float:
    """W50 tại tần số quan sát (ms) = giãn nội tại (∝ ν^-α) ⊕ tán xạ."""
    w_int = w50_1400_ms * (1400.0 / f_mhz) ** alpha_w
    return _math.hypot(w_int, tau_scattering_ms(dm, f_mhz))


PULSARS = [
    dict(name="B0950+08", pdot=2.3e-16, ra=148.2888, dec=7.9266, P=0.253065, dm=2.97,
         s408=400, s1400=100, w1400=8.6,
         note="Sáng, DM thấp, gần thiên đỉnh 87° — MỤC TIÊU #1 cho L-band"),
    dict(name="B1929+10", pdot=1.16e-15, ra=292.0, dec=10.9833, P=0.226518, dm=3.18,
         s408=303, s1400=29, w1400=6.0,
         note="Gần thiên đỉnh 90°, DM thấp, nhưng yếu ở 1.4 GHz"),
    dict(name="B1133+16", pdot=3.73e-15, ra=174.0, dec=15.8167, P=1.187935, dm=4.84,
         s408=257, s1400=20, w1400=5.8,
         note="P dài, dễ fold, cao 85°; sáng ở 423 MHz hơn 1.4 GHz"),
    dict(name="B0329+54", pdot=2e-15, ra=53.2475, dec=54.5788, P=0.714519, dm=26.76,
         s408=1500, s1400=203, w1400=6.6,
         note="RẤT sáng (1.5 Jy @400 MHz) — mục tiêu chủ lực, dù altmax 46°"),
    dict(name="B0833-45", pdot=1.25e-13, ra=128.8358, dec=-45.1764, P=0.089328, dm=67.94,
         s408=5000, s1400=1050, w1400=1.7,
         note="Vela — SÁNG NHẤT (5 Jy @400, 1.05 Jy @1400); altmax 34°"),
    dict(name="B0531+21", pdot=4.21e-13, ra=83.6332, dec=22.0145, P=0.033392, dm=56.77,
         s408=646, s1400=14, w1400=3.0,
         note="Cua — mạnh ở 423 MHz, RẤT yếu ở L-band (14 mJy); có giant pulse"),
    dict(name="J0437-4715", pdot=5.73e-20, ra=69.3163, dec=-47.2525, P=0.005757, dm=2.644,
         s408=550, s1400=150.2, w1400=0.141,
         note="MSP sáng nhất; P 5,76 ms → cần đồng hồ tốt, xung rất hẹp"),
    dict(name="B1641-45", pdot=1.02e-14, ra=251.2054, dec=-45.9867, P=0.455, dm=478.7,
         s408=375, s1400=300, w1400=8.0,
         note="DM 479 → tán xạ xóa sạch ở 423 MHz, nhưng QUAN SÁT ĐƯỢC ở L-band"),
    dict(name="B1706-44", pdot=9.41e-14, ra=257.4280, dec=-44.4856, P=0.102476, dm=75.58,
         s408=25, s1400=12.1, w1400=6.0,
         note="Trẻ nhưng rất yếu ở vô tuyến (25 mJy @400) — không khả thi"),
    dict(name="B1937+21", pdot=1.05e-19, ra=294.9107, dec=21.5831, P=0.0015578, dm=71.02,
         s408=240, s1400=13.9, w1400=0.0382,
         note="MSP 1,56 ms — thử thách đồng hồ và tsamp cực đại"),
]

# sinh w408 từ mô hình (không chép tay) để mọi bảng SNR dùng cùng một nguồn
for _t in PULSARS:
    _t["w408"] = round(w50_at(_t["w1400"], _t["dm"], 423.0), 2)

# ---------------------------------------------------------------- toạ độ/giờ
def jd_from_datetime(dt: datetime) -> float:
    """JD (UTC). Nếu dt không có tz thì hiểu là giờ ĐỊA PHƯƠNG (UTC+7)."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone(timedelta(hours=TZ_H)))
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    return 2440587.5 + (dt - epoch).total_seconds() / 86400.0


def lst_deg(jd, lon_deg=None):
    lon_deg = LON_DEG if lon_deg is None else lon_deg
    d = np.asarray(jd) - 2451545.0
    gmst = 280.46061837 + 360.98564736629 * d
    return (gmst + lon_deg) % 360.0


def alt_deg(ra_deg, dec_deg, jd, lat_deg=None):
    lat_deg = LAT_DEG if lat_deg is None else lat_deg
    ha = np.radians(lst_deg(jd) - ra_deg)
    dec = math.radians(dec_deg)
    lat = math.radians(lat_deg)
    s = (math.sin(dec) * math.sin(lat)
         + math.cos(dec) * math.cos(lat) * np.cos(ha))
    return np.degrees(np.arcsin(np.clip(s, -1, 1)))


def altitude_curve(ra_deg, dec_deg, day: datetime, hours=10.0, step_min=10,
                   start_hour=19.0):
    t0 = day.replace(hour=int(start_hour), minute=0, second=0, microsecond=0)
    dt_list = [t0 + timedelta(minutes=step_min * i)
               for i in range(int(hours * 60 / step_min) + 1)]
    jd = np.array([jd_from_datetime(d) for d in dt_list])
    alt = alt_deg(ra_deg, dec_deg, jd)
    return np.array(dt_list), alt


def best_month(ra_deg, dec_deg, alt_min=30.0):
    """Tháng có nhiều giờ nhất với độ cao > alt_min trong đêm."""
    best = (0.0, None, 0.0)
    for m in range(1, 13):
        hours = []
        for d in (1, 8, 15, 22):
            day = datetime(2026, m, d)
            _, alt = altitude_curve(ra_deg, dec_deg, day)
            hours.append(float(np.sum(alt > alt_min)) * 10 / 60)
        h = float(np.mean(hours))
        hmax = max(hours)
        if h > best[0]:
            best = (h, m, hmax)
    return best


def alt_max(dec_deg, lat_deg=None):
    lat_deg = LAT_DEG if lat_deg is None else lat_deg
    return 90.0 - abs(lat_deg - dec_deg)


# ------------------------------------------------- DANH MỤC MỤC TIÊU TỰ THÊM
# Người dùng có thể quan sát pulsar KHÔNG có trong PULSARS (pulsar mới hoặc
# mục tiêu tự đặt). Danh mục tự thêm lưu ở targets_user.json
# cạnh ứng dụng — thêm/sửa/xoá ngay trong GUI, không cần sửa code.
import json
import re as _re
import sys as _sys


def app_dir() -> str:
    """Thư mục ghi được (chạy mã nguồn hay EXE đều đúng)."""
    if getattr(_sys, "frozen", False):
        return os.path.dirname(_sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def user_targets_path() -> str:
    return os.environ.get("PSR_TARGETS_FILE") or os.path.join(
        app_dir(), "targets_user.json")


def load_user_targets() -> list:
    """Đọc danh mục tự thêm; file hỏng/thiếu → danh sách rỗng (không crash)."""
    path = user_targets_path()
    if not os.path.exists(path):
        return []
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        items = data.get("targets", []) if isinstance(data, dict) else data
        out = []
        for t in items:
            if isinstance(t, dict) and t.get("name"):
                t = dict(t)
                t["custom"] = True
                out.append(t)
        return out
    except Exception as exc:
        print(f"⚠ không đọc được {path}: {exc!r} — bỏ qua danh mục tự thêm")
        return []


def save_user_targets(items: list) -> None:
    path = user_targets_path()
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"version": 1, "targets": items}, fh,
                  ensure_ascii=False, indent=2)


def all_pulsars() -> list:
    """PULSARS (có sẵn) + mục tiêu tự thêm. Tự thêm TRÙNG TÊN thì thay thế."""
    user = load_user_targets()
    names = {str(t["name"]).strip().lower() for t in user}
    out = [dict(t, custom=False) for t in PULSARS
           if str(t["name"]).strip().lower() not in names]
    out.extend(user)
    return out


def find_target(name: str, items: list | None = None) -> dict | None:
    """Tra mục tiêu theo tên (không phân biệt hoa/thường, bỏ khoảng trắng)."""
    if not name:
        return None
    key = str(name).strip().lower()
    for t in (items if items is not None else all_pulsars()):
        if str(t.get("name", "")).strip().lower() == key:
            return t
    return None


def upsert_target(t: dict) -> dict:
    """Thêm mới hoặc cập nhật (theo tên) một mục tiêu tự thêm."""
    problems = validate_target(t)
    if problems:
        raise ValueError("; ".join(problems))
    items = load_user_targets()
    keys = ("name", "ra", "dec", "P", "dm", "pdot",
            "s408", "s1400", "w408", "w1400", "note")
    item = {k: t[k] for k in keys if t.get(k) not in (None, "")}
    item["name"] = str(item["name"]).strip()
    item["custom"] = True
    key = item["name"].lower()
    for i, old in enumerate(items):
        if str(old.get("name", "")).strip().lower() == key:
            items[i] = item
            break
    else:
        items.append(item)
    save_user_targets(items)
    return item


def delete_target(name: str) -> bool:
    items = load_user_targets()
    key = str(name).strip().lower()
    keep = [t for t in items if str(t.get("name", "")).strip().lower() != key]
    if len(keep) == len(items):
        return False
    save_user_targets(keep)
    return True


def parse_ra(text: str) -> float:
    """RA → độ. "HH:MM:SS" (giờ) hoặc số thực (độ).

    Quy ước: CÓ dấu ':' là giờ-phút-giây; chỉ có số thì là ĐỘ.
    """
    t = str(text).strip().replace("h", ":").replace("m", ":").replace("s", "")
    if not t:
        raise ValueError("RA trống")
    if ":" in t:
        parts = [p for p in _re.split(r"[:\s]+", t) if p]
        if len(parts) > 3:
            raise ValueError("RA có quá 3 phần")
        vals = [float(x) for x in parts] + [0.0] * (3 - len(parts))
        h, m, sec = vals[0], vals[1], vals[2]
        if not (0 <= h < 24 and 0 <= m < 60 and 0 <= sec < 60):
            raise ValueError("RA ngoài khoảng (giờ 0–24, phút/giây 0–60)")
        return (h + m / 60 + sec / 3600) * 15.0
    v = float(t)
    if not (0 <= v < 360):
        raise ValueError("RA (độ) phải trong [0, 360)")
    return v


def parse_dec(text: str) -> float:
    """Dec → độ. "±DD:MM:SS" hoặc số thực (độ)."""
    t = str(text).strip().replace("d", ":").replace("m", ":").replace("s", "")
    t = t.replace("−", "-").replace("–", "-")
    if not t:
        raise ValueError("Dec trống")
    sign = -1.0 if t.startswith("-") else 1.0
    body = t.lstrip("+-")
    if ":" in body:
        parts = [p for p in _re.split(r"[:\s]+", body) if p]
        vals = [float(x) for x in parts] + [0.0] * (3 - len(parts))
        d, m, sec = vals[0], vals[1], vals[2]
        if not (0 <= d <= 90 and 0 <= m < 60 and 0 <= sec < 60):
            raise ValueError("Dec ngoài khoảng (độ 0–90, phút/giây 0–60)")
        return sign * (d + m / 60 + sec / 3600)
    v = sign * float(body)
    if not (-90 <= v <= 90):
        raise ValueError("Dec phải trong [-90, +90]")
    return v


def validate_target(t: dict) -> list:
    """Trả về danh sách lỗi (rỗng = hợp lệ)."""
    problems = []
    name = str(t.get("name", "")).strip()
    if not name:
        problems.append("thiếu tên mục tiêu")
    elif len(name) > 24:
        problems.append("tên quá dài (>24 ký tự)")
    elif any(c in name for c in '\\/:*?"<>|'):
        problems.append('tên chứa ký tự không hợp lệ \\ / : * ? " < > |')
    try:
        ra = float(t.get("ra"))
        if not (0 <= ra < 360):
            problems.append("RA phải trong [0, 360) độ")
    except (TypeError, ValueError):
        problems.append("RA không hợp lệ")
    try:
        dec = float(t.get("dec"))
        if not (-90 <= dec <= 90):
            problems.append("Dec phải trong [-90, +90] độ")
    except (TypeError, ValueError):
        problems.append("Dec không hợp lệ")
    for key, label in (("P", "chu kỳ P (s)"), ("dm", "DM (pc cm-3)"),
                       ("s408", "flux 408 MHz (mJy)"),
                       ("s1400", "flux 1400 MHz (mJy)"),
                       ("w408", "W50 408 MHz (ms)"),
                       ("w1400", "W50 1400 MHz (ms)")):
        v = t.get(key)
        if v in (None, ""):
            continue
        try:
            if float(v) < 0:
                problems.append(f"{label} phải ≥ 0")
        except (TypeError, ValueError):
            problems.append(f"{label} không phải số")
    return problems


# ------------------------------------------------------------------- cấu hình
CONFIGS = [
    Config("A: RTL-SDR + SAWbird+HI (hiện có)", 1420, 2.4, 150, 64, 104),
    Config("B: SDR 10 MHz @ L-band", 1400, 10.0, 130, 256, 25),
    Config("C: SDR 40 MHz @ L-band (nâng cấp)", 1400, 40.0, 120, 512, 16),
    Config("D: 408 MHz + RTL-SDR (FE mới)", 408, 2.4, 300, 64, 104),
    Config("E: 408 MHz + SDR 8 MHz", 408, 8.0, 250, 256, 32),
]


def pick_flux(t, f_mhz):
    """Flux (Jy) + W50 (s) tại tần số quan sát; (None, None) nếu thiếu dữ liệu."""
    hi = f_mhz >= 800
    s = t.get("s1400") if hi else t.get("s408")
    w = t.get("w1400") if hi else t.get("w408")
    if s is None or w is None:
        return None, None
    return float(s) / 1e3, float(w) / 1e3


def table_pulsars(csv_path=None):
    dish = Dish()
    rows = []
    for t in all_pulsars():
        amax = alt_max(t["dec"])
        hbest, month, _ = best_month(t["ra"], t["dec"])
        row = dict(name=t["name"],
                   P_ms=(t["P"] * 1e3) if t.get("P") else None,
                   dm=t.get("dm"), alt_max=round(amax, 1), best_month=month,
                   h_above30=round(hbest, 1), note=t.get("note", ""))
        for cfg in CONFIGS:
            sefd = dish.sefd_jy(cfg.tsys_k)
            s, w = pick_flux(t, cfg.f_mhz)
            key = cfg.name.split(":")[0]
            if s is None or w is None or not t.get("P"):
                row[f"SNR1h_{key}"] = row[f"SNR6h_{key}"] = None
                continue
            row[f"SNR1h_{key}"] = round(snr_fold(s, sefd, cfg.bw_mhz * 1e6,
                                                 3600, t["P"], w), 2)
            row[f"SNR6h_{key}"] = round(snr_fold(s, sefd, cfg.bw_mhz * 1e6,
                                                 6 * 3600, t["P"], w), 2)
        rows.append(row)
    if csv_path:
        os.makedirs(RESULTS, exist_ok=True)
        with open(csv_path, "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
    return rows


def print_pulsars(rows):
    print(f"\nNgười quan sát: lat {LAT_DEG}°N, lon {LON_DEG}°E — "
          f"chảo 3.7 m, eta 0.55, G = 2.14 mK/Jy")
    for cfg in CONFIGS:
        key = cfg.name.split(":")[0]
        sefd = Dish().sefd_jy(cfg.tsys_k)
        dmres = chan_smear_ms(26.8, cfg.chan_width_mhz, cfg.f_mhz)
        print(f"\n=== {cfg.name}  |  B = {cfg.bw_mhz} MHz, Tsys = {cfg.tsys_k} K, "
              f"SEFD = {sefd/1e3:.1f} kJy, trải/kênh(DM=27) = {dmres:.2f} ms")
        print(f"{'pulsar':>11} {'P(ms)':>7} {'DM':>6} {'altmax':>6} {'tháng':>5} "
              f"{'h>30°':>5} {'SNR 1h':>7} {'SNR 6h':>7}  kết luận")
        for r in rows:
            s1, s6 = r[f"SNR1h_{key}"], r[f"SNR6h_{key}"]
            p_ms = "—" if r["P_ms"] is None else f"{r['P_ms']:7.1f}"
            dm = "—" if r["dm"] is None else f"{r['dm']:6.1f}"
            if s1 is None or s6 is None:
                s1s, s6s, vd = "      —", "      —", "thiếu P/DM/flux"
            else:
                s1s, s6s, vd = f"{s1:7.2f}", f"{s6:7.2f}", verdict(s6, 6 * 3600)
            print(f"{r['name']:>11} {p_ms} {dm} "
                  f"{r['alt_max']:>6.1f} {r['best_month']:>5} {r['h_above30']:>5.1f} "
                  f"{s1s} {s6s}  {vd}")
    print("\n(Lưu ý: 1 giờ quan sát thực tế chỉ đạt ~60–70% thời gian trên do "
          "hiệu chuẩn + trỏ + mất mẫu; hãy nhân thêm hệ số 0.7.)")


def derived(pdot: float, P: float, dm: float) -> dict:
    """P-dot → từ trường, tuổi, công suất mất năng lượng; DM → khoảng cách.

    B_s   = 3.2e19 * sqrt(P * Pdot)              [G]   (dipole, xích đạo)
    tau   = P / (2 Pdot)                          [yr]  (tuổi đặc trưng)
    Edot  = 4 pi^2 I Pdot / P^3, I = 1e38 kg m^2 [W]
    d_DM  = DM / <n_e>, <n_e> = 0.03 cm^-3       [pc]  (bậc độ lớn)
    """
    import math
    B = 3.2e19 * math.sqrt(max(P * pdot, 0.0))
    tau = P / (2 * pdot) / 3.15576e7 if pdot > 0 else float("inf")
    I = 1e38
    edot = 4 * math.pi**2 * I * pdot / P**3
    return {"B_G": B, "age_yr": tau, "Edot_W": edot,
            "d_kpc": dm / 0.03 / 1e3}


def print_derived():
    print("\n=== Đại lượng suy ra từ P, P-dot, DM (giá trị ATNF xấp xỉ) ===")
    print(f"{'pulsar':>11} {'P(ms)':>8} {'Pdot':>10} {'B(G)':>9} {'tuổi(yr)':>11} "
          f"{'Edot(W)':>10} {'d_DM(kpc)':>10}  loại")
    dish = Dish()
    for t in all_pulsars():
        if t.get("P") is None or t.get("pdot") is None or t.get("dm") is None:
            print(f"{t['name']:>11}  (thiếu P / P-dot / DM — không tính được)")
            continue
        d = derived(t["pdot"], t["P"], t["dm"])
        kind = "MSP" if t["P"] < 0.03 else ("trẻ" if d["age_yr"] < 1e5 else "thường")
        print(f"{t['name']:>11} {t['P']*1e3:>8.1f} {t['pdot']:>10.2e} "
              f"{d['B_G']:>9.2e} {d['age_yr']:>11.2e} {d['Edot_W']:>10.2e} "
              f"{d['d_kpc']:>10.1f}  {kind}")
    print("\nLưu ý: B giả định lưỡng cực; tuổi đặc trưng ≠ tuổi thật (pulsar tái"
          " gia tốc có tuổi ảo rất lớn); d_DM chỉ đúng bậc độ lớn vì <n_e> thay đổi"
          " 0.01–0.1 cm^-3 theo hướng.")


# --------------------------------------------------- Mặt Trời & quan sát BAN NGÀY
def sun_ra_dec(jd) -> tuple[np.ndarray, np.ndarray]:
    """Vị trí Mặt Trời (xấp xỉ thấp, sai số < 0.02° — quá đủ để tính góc tránh).

    Công thức chuẩn (Astronomical Almanac, low-precision):
        L = 280.460° + 0.9856474°·n ;  g = 357.528° + 0.9856003°·n
        λ = L + 1.915°·sin g + 0.020°·sin 2g ;  ε = 23.439° − 4e-7·n
    """
    n = np.asarray(jd, dtype=float) - 2451545.0
    L = np.radians(280.460 + 0.9856474 * n)
    g = np.radians(357.528 + 0.9856003 * n)
    lam = L + np.radians(1.915) * np.sin(g) + np.radians(0.020) * np.sin(2 * g)
    eps = np.radians(23.439 - 4e-7 * n)
    ra = np.degrees(np.arctan2(np.cos(eps) * np.sin(lam), np.cos(lam))) % 360.0
    dec = np.degrees(np.arcsin(np.sin(eps) * np.sin(lam)))
    return ra, dec


def sep_deg(ra1, dec1, ra2, dec2):
    """Góc tách (độ) giữa hai hướng trên thiên cầu."""
    r = np.radians
    c = (np.sin(r(dec1)) * np.sin(r(dec2))
         + np.cos(r(dec1)) * np.cos(r(dec2)) * np.cos(r(ra1) - r(ra2)))
    return np.degrees(np.arccos(np.clip(c, -1, 1)))


def daytime_windows(ra_deg, dec_deg, day: datetime, min_sep=45.0, min_alt=25.0,
                    step_min=5):
    """Các khoảng THỜI GIAN BAN NGÀY quan sát được (Mặt Trời đã mọc).

    Điều kiện: độ cao mục tiêu > min_alt, Mặt Trời trên đường chân trời,
    và góc tách Mặt Trời–mục tiêu > min_sep (tránh nhiễu + tránh hỏng LNA).
    Trả về list[(t_bắt_đầu, t_kết_thúc, h_giờ)].
    """
    t0 = day.replace(hour=0, minute=0, second=0, microsecond=0)
    n = int(24 * 60 / step_min)
    ts = [t0 + timedelta(minutes=step_min * i) for i in range(n + 1)]
    jd = np.array([jd_from_datetime(t) for t in ts])
    alt = alt_deg(ra_deg, dec_deg, jd)
    sra, sdec = sun_ra_dec(jd)
    # độ cao Mặt Trời TẠI NƠI QUAN SÁT (không dùng alt_deg vì hàm đó nhận dec vô hướng)
    salt = np.degrees(np.arcsin(np.clip(
        np.sin(np.radians(sdec)) * np.sin(np.radians(LAT_DEG))
        + np.cos(np.radians(sdec)) * np.cos(np.radians(LAT_DEG))
        * np.cos(np.radians(lst_deg(jd) - sra)), -1, 1)))
    sep = sep_deg(ra_deg, dec_deg, sra, sdec)
    ok = (alt > min_alt) & (salt > 0) & (sep > min_sep)
    out, i = [], 0
    while i < len(ok):
        if ok[i]:
            j = i
            while j + 1 < len(ok) and ok[j + 1]:
                j += 1
            out.append((ts[i], ts[j], (j - i + 1) * step_min / 60))
            i = j + 1
        else:
            i += 1
    return out


def print_daytime(date_str=None, min_sep=45.0, min_alt=25.0):
    day = (datetime.fromisoformat(date_str) if date_str
           else datetime.now()).replace(hour=0, minute=0, second=0, microsecond=0)
    jd0 = jd_from_datetime(day.replace(hour=12))
    sra, sdec = sun_ra_dec(jd0)
    print(f"\n=== Quan sát BAN NGÀY — ngày {day.date()} ===")
    print(f"Mặt Trời: RA = {float(sra):6.1f}°  Dec = {float(sdec):+5.1f}°  "
          f"→ các mục tiêu gần RA này đi qua trung tuyến lúc giữa trưa")
    print(f"Điều kiện: độ cao > {min_alt:.0f}°, Mặt Trời đã mọc, "
          f"tách Mặt Trời > {min_sep:.0f}°")
    rows = []
    for t in all_pulsars():
        w = daytime_windows(t["ra"], t["dec"], day, min_sep, min_alt)
        h = sum(x[2] for x in w)
        best = max(w, key=lambda x: x[2]) if w else None
        rows.append((h, t["name"], best))
    rows.sort(reverse=True)
    print(f"{'pulsar':>11} {'h ban ngày':>10}  cửa sổ tốt nhất (giờ địa phương)")
    for h, name, best in rows:
        if best is None:
            print(f"{name:>11} {0.0:>10.1f}  —")
        else:
            print(f"{name:>11} {h:>10.1f}  {best[0]:%H:%M} → {best[1]:%H:%M} "
                  f"({best[2]:.1f} h)")
    print("\nLưu ý: ban ngày KHÔNG làm nền trời vô tuyến sáng lên — chỉ Mặt Trời là")
    print("nguồn nhiễu, và nó ở MỘT hướng. Giữ tách > 45° là đủ. Nhưng gain/RFI trôi")
    print("theo nhiệt độ ban ngày → phải hiệu chuẩn lại mỗi 30–45 phút.")


# ------------------------------------------------- CHE DO NGAM CO DINH (transit)
def transit_local(ra_deg, day: datetime):
    """Gio dia phuong khi nguon di qua trung tuyen (LST = RA), do phan giai 1 phut."""
    t0 = day.replace(hour=0, minute=0, second=0, microsecond=0)
    best, best_dt = None, 1e9
    for i in range(24 * 60):
        t = t0 + timedelta(minutes=i)
        d = (float(lst_deg(jd_from_datetime(t))) - ra_deg + 180.0) % 360.0 - 180.0
        if abs(d) < best_dt:
            best, best_dt = t, abs(d)
    return best


def teff_transit_h(hpbw_deg: float, dec_deg: float) -> float:
    """Thoi gian TÍCH LUỸ HIỆU DỤNG khi de yen chao, nguon tu di qua chum tia.

    Voi chum Gauss, SNR^2 ~ tich phan do loi -> T_eff = 1.064*HPBW/v_troi,
    v_troi = 15.041 deg/gio * cos(dec).  Day la con so DUNG de tinh SNR,
    khong phai 'so gio chao bat'.
    """
    v = 15.041 * math.cos(math.radians(dec_deg))
    return 1.064 * hpbw_deg / v


def print_transit(date_str=None, bw_mhz=20.0, tsys=200.0, hpbw=13.4):
    day = (datetime.fromisoformat(date_str) if date_str
           else datetime.now()).replace(hour=0, minute=0, second=0, microsecond=0)
    dish = Dish()
    print(f"\n=== CHE DO NGAM CO DINH (transit) — ngay {day.date()} ===")
    print(f"Gia dinh: 423 MHz, HPBW {hpbw:.1f} do, B = {bw_mhz:.0f} MHz, Tsys = {tsys:.0f} K")
    print(f"{'pulsar':>11} {'transit':>8} {'el':>6} {'T_eff@423':>10} {'SNR/transit':>12} "
          f"{'dem can':>8}")
    for t in all_pulsars():
        tr = transit_local(t["ra"], day)
        el = float(alt_deg(t["ra"], t["dec"], jd_from_datetime(tr)))
        te = teff_transit_h(hpbw, t["dec"])
        s, w = pick_flux(t, 423.0)
        sefd = dish.sefd_jy(tsys)
        if s is None or w is None or not t.get("P"):
            print(f"{t['name']:>11} {tr:%H:%M} {el:>6.1f} {te:>9.2f}h "
                  f"{'—':>12} {'—':>8}  (thiếu flux/P)")
            continue
        snr1 = snr_fold(s, sefd, bw_mhz * 1e6, te * 3600, t["P"], w)
        n = math.ceil((8.0 / snr1) ** 2) if snr1 > 0 else 99
        print(f"{t['name']:>11} {tr:%H:%M} {el:>6.1f} {te:>9.2f}h {snr1:>12.1f} "
              f"{n:>8}")
    print("\nN_dem = so dem transit can cong don de dat SNR 8 (SNR ~ sqrt(N)).")
    print("Luu y: chao bat ca dem nhung chi ~1 gio la co ich -> phai cat theo cua so")
    print("transit va trong so theo do loi chum tia, dung cong don ca dem.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--derived", action="store_true")
    ap.add_argument("--daytime", action="store_true")
    ap.add_argument("--transit", action="store_true")
    ap.add_argument("--bw", type=float, default=20.0)
    ap.add_argument("--date", default=None, help="YYYY-MM-DD cho --daytime")
    ap.add_argument("--min-sep", type=float, default=45.0)
    ap.add_argument("--csv", action="store_true")
    a = ap.parse_args()
    ensure_utf8_stdout()
    if a.transit:
        print_transit(a.date, a.bw)
    elif a.daytime:
        print_daytime(a.date, a.min_sep)
    elif a.derived:
        print_derived()
    else:
        path = os.path.join(RESULTS, "targets.csv") if a.csv else None
        print_pulsars(table_pulsars(path))
        if path:
            print(f"\n→ đã ghi {path}")
