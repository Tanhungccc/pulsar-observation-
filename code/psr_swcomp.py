# -*- coding: utf-8 -*-
"""
psr_swcomp.py — BÙ TRỪ BẰNG PHẦN MỀM cho chuỗi phần cứng TỐI GIẢN.

Triết lý (theo yêu cầu "tối giản phần cứng, bù đắp bằng phần mềm"):
    Phần cứng chỉ giữ 3 thứ BẮT BUỘC: feed + LNA + SDR. Mọi thứ khác
    (bộ lọc, GPSDO, motor, hiệu chuẩn) có thể giảm thiểu và bù bằng phần mềm
    — TRỪ ba giới hạn vật lý không bù được, ghi rõ trong LIMITS.

Registry bù trừ (compensation registry):
    thiếu phần cứng        → phần mềm bù                   → mức thiệt hại còn lại
    ----------------------------------------------------------------------------
    BPF (lọc dải)          → masking kênh + zero-DM v2     → ADC vẫn có thể bão hoà
    GPSDO (đồng hồ)         → đo ppm từ pulsar catalogue   → timing dài vẫn yếu
    Motor + encoder         → transit + trọng số chùm       → mất 35-45% thời gian
    LNA ngoài (hỏng)       → gain nội SDR + stacking đêm   → T_sys ×8 (không cứu)
    Hiệu chuẩn vị trí      → Cas A 3 điểm tự động          → ±0.3°
    Nguồn chuẩn nhiệt       → Y-factor tự động              → ±10% SEFD

API chính:
    measure_ppm()        — đo sai số đồng hồ từ chu kỳ quan sát vs catalogue
    barycentric_delay_s()— hiệu chỉnh về tâm Hệ Mặt Trời (astropy, nếu có)
    transit_weights()    — trọng số chùm Gauss cho chế độ ngắm cố định
    stack_profiles()     — cộng dồn hồ sơ nhiều đêm (trọng số nghịch phương sai)
    nightly_plan()       — sinh kế hoạch phiên ngắn (4-5 h) cho mục tiêu
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

K_DM = 4.148808e3

# ---- GIỚI HẠN VẬT LÝ: phần mềm KHÔNG bù được -------------------------------
LIMITS = [
    ("Diện tích chảo A_eff", "SNR ∝ A_eff", "chỉ nâng cấp phần cứng"),
    ("Độ ồn LNA / T_sys", "SNR ∝ 1/T_sys", "thay LNA — phần mềm không giảm được"),
    ("Băng thông B", "SNR ∝ √B", "thay SDR — chỉ phần cứng"),
    ("Bão hoà ADC do RFI ngoài dải", "méo toàn phổ", "bắt buộc có BPF vật lý"),
    ("Phân cực (1 hay 2)", "không đo RM được", "cần feed 2 phân cực"),
]

# ---- registry bù trừ ------------------------------------------------------
COMPENSATIONS = {
    "bpf": dict(missing="BPF/lọc dải",
                software="masking kênh + zero-DM phổ phẳng + cắt biên dải",
                module="psr_core.zero_dm_excise / mask_bad_channels",
                residual="ADC vẫn có thể bão hoà nếu RFI quá mạnh"),
    "gpsdo": dict(missing="GPSDO",
                  software="đo ppm từ chu kỳ pulsar catalogue + refine_period",
                  module="psr_swcomp.measure_ppm / psr_core.refine_period",
                  residual="timing nhiều tháng vẫn cần GPSDO"),
    "motor": dict(missing="Motor + encoder",
                  software="transit + trọng số chùm Gauss + UTC chính xác",
                  module="psr_swcomp.transit_weights / psr_targets.print_transit",
                  residual="chỉ ~40-55% thời gian treo là hữu ích"),
    "lna_outer": dict(missing="LNA ngoài (hỏng)",
                      software="gain nội SDR + cộng dồn nhiều đêm",
                      module="psr_swcomp.stack_profiles",
                      residual="T_sys tăng ~8 lần — không cứu được"),
    "cal_source": dict(missing="Nguồn hiệu chuẩn",
                       software="Y-factor tự động bằng Cas A / Mặt Trăng",
                       module="psr_swcomp.y_factor_tsys",
                       residual="sai số SEFD ±10-15%"),
    "clock_model": dict(missing="Mô hình đồng hồ/địa tâm",
                        software="hiệu chỉnh barycentric bằng astropy (nếu cài)",
                        module="psr_swcomp.barycentric_delay_s",
                        residual="thiếu astropy thì bỏ qua cho t < 1 h"),
}


# ---------------------------------------------------------------- đồng hồ
def measure_ppm(period_obs_s: float, period_cat_s: float) -> float:
    """Sai số đồng hồ (ppm) từ chu kỳ đo được so với catalogue.

    ppm = (P_đo − P_cat)/P_cat × 1e6.  Dùng để hiệu chỉnh SDR cho các đêm sau:
    P_dùng = P_cat × (1 + ppm/1e6) khi chưa có GPSDO.
    """
    return (period_obs_s - period_cat_s) / period_cat_s * 1e6


def correct_period(period_cat_s: float, ppm: float) -> float:
    """Chu kỳ đã hiệu chỉnh đồng hồ cho lần quan sát tiếp theo."""
    return period_cat_s * (1.0 + ppm * 1e-6)


# ---------------------------------------------------------------- barycentric
def barycentric_delay_s(ra_deg: float, dec_deg: float, t_utc,
                        lat_deg: float = 10.7769, lon_deg: float = 106.7009,
                        alt_m: float = 10.0) -> float | None:
    """Độ trễ barycentric (giây) cần TRỪ khỏi thời gian quan sát.

    Dùng astropy nếu có; trả None nếu không cài (khi đó fold ngắn vẫn ổn,
    nhưng timing dài bị sai). Công thức: chiếu vector Trái Đất→Mặt Trời
    lên hướng nguồn, chia c.
    """
    try:
        from astropy.time import Time
        from astropy.coordinates import SkyCoord, EarthLocation
        import astropy.units as u
    except Exception:
        return None
    loc = EarthLocation(lat=lat_deg * u.deg, lon=lon_deg * u.deg,
                        height=alt_m * u.m)
    c = SkyCoord(ra_deg * u.deg, dec_deg * u.deg)
    t = Time(t_utc, scale="utc", location=loc)
    _, light_travel_time = t.light_travel_time(c, kind="barycentric").jd, \
        t.light_travel_time(c, kind="barycentric")
    return float(light_travel_time.to(u.s).value)


# ---------------------------------------------------------------- transit
def transit_weights(n: int, hpbw_deg: float, t_total_s: float,
                    cos_dec: float = 1.0) -> np.ndarray:
    """Trọng số chùm Gauss cho chế độ ngắm cố định (transit).

    w(t) = exp(−4 ln2 · (θ(t)/HPBW)²), θ(t) = góc cách trục chùm =
    (t − t_transit) · 15.041°/h · cos δ.  Trọng số này thay cho việc
    "cộng đều cả đêm" (sai): mẫu ngoài chùm chỉ thêm nhiễu.
    """
    t = (np.arange(n) - (n - 1) / 2.0) / n * t_total_s    # giây, 0 = transit
    theta = t * (15.041 / 3600.0) * cos_dec                # độ
    return np.exp(-4.0 * math.log(2.0) * (theta / hpbw_deg) ** 2)


# ---------------------------------------------------------------- stacking
def stack_profiles(profiles, weights=None) -> tuple[np.ndarray, float]:
    """Cộng dồn hồ sơ xung nhiều đêm: SNR_cũ ∝ √(Σ w·t).

    profiles: list hồ sơ (đã cùng số bin, cùng pha!)
    weights : mặc định 1/σ² của nền mỗi hồ sơ (nghịch phương sai).
    Trả về (hồ sơ gộp, SNR ước lượng).
    """
    arr = np.array([np.asarray(p, dtype=float) for p in profiles])
    if weights is None:
        sig = np.array([1.4826 * np.median(np.abs(p - np.median(p)))
                        + 1e-12 for p in arr])
        weights = 1.0 / sig**2
    w = np.asarray(weights, dtype=float)
    prof = (arr * w[:, None]).sum(axis=0) / w.sum()
    med = np.median(prof)
    rms = 1.4826 * np.median(np.abs(prof - med)) + 1e-12
    snr = float((prof.max() - med) / rms)
    return prof, snr


# ---------------------------------------------------------------- Y-factor
def y_factor_tsys(p_on: float, p_off: float, t_cal_k: float = 2.7) -> tuple[float, float]:
    """Y-factor: T_sys từ đo trên/dưới nguồn chuẩn (Cas A).

    Y = P_on/P_off ; T_sys = T_cal/(Y − 1).  Trả về (T_sys, T_cal đã biết).
    Lưu ý: T_cal = nhiệt độ ăng-ten của nguồn (Cas A ~ 5.8 K với chảo 3.7 m).
    """
    y = p_on / p_off
    if y <= 1.0:
        raise ValueError("P_on phải > P_off (Y ≤ 1) — kiểm tra phép đo")
    return t_cal_k / (y - 1.0), t_cal_k


# ---------------------------------------------------------------- kế hoạch
@dataclass
class Session:
    night: int
    start_utc: str
    hours: float
    role: str          # 'observe' | 'calibrate'
    notes: str = ""


def nightly_plan(target: str, total_hours: float, session_h: float = 2.5,
                 n_cal: int = 2) -> list[Session]:
    """Kế hoạch nhiều phiên ngắn (mặc định 2.5 h/phiên, thêm Cas A 2 đầu).

    Mỗi phiên độc lập: fold riêng rồi stack_profiles() → không cần GPSDO
    nếu mục tiêu có P đã biết chính xác (catalogue).
    """
    plan = [Session(0, "T−30 phút", 0.5, "calibrate", "Cas A đầu buổi")]
    n = math.ceil(total_hours / session_h)
    for i in range(n):
        plan.append(Session(i + 1, f"đêm {i+1}", session_h, "observe", target))
    plan.append(Session(n + 1, "sau đêm cuối", 0.5, "calibrate", "Cas A cuối"))
    return plan


if __name__ == "__main__":
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    print("=== GIỚI HẠN VẬT LÝ (phần mềm không bù được) ===")
    for name, scaling, fix in LIMITS:
        print(f"  • {name}: {scaling} → {fix}")
    print("\n=== REGISTRY BÙ TRỪ PHẦN MỀM ===")
    for k, v in COMPENSATIONS.items():
        print(f"  [{k}] thiếu {v['missing']}")
        print(f"       bù: {v['software']}  ({v['module']})")
        print(f"       còn lại: {v['residual']}")

    print("\n=== Ví dụ: đo ppm ===")
    ppm = measure_ppm(0.7145202, 0.714519699557)
    print(f"  P_đo = 0.7145202 s, P_cat = 0.714519699557 s → {ppm:+.2f} ppm")
    print(f"  P hiệu chỉnh cho đêm sau: {correct_period(0.714519699557, ppm):.9f} s")

    print("\n=== Ví dụ: trọng số transit (3.7 m @423 MHz, HPBW 13.4°) ===")
    w = transit_weights(400, 13.4, 4 * 3600.0, cos_dec=math.cos(math.radians(7.93)))
    teff = w.sum() * (4 * 3600.0 / 400) / 3600.0
    print(f"  T_eff = {teff:.2f} h (cửa sổ ±2 h; công thức = 0.96 h — ")
    print(f"  phần lớn năng lượng chùm nằm trong ±1.5 h quanh transit)")

    print("\n=== Ví dụ: stack 4 đêm 2.5 h ===")
    rng = np.random.default_rng(0)
    profs = []
    for i in range(4):
        p = rng.normal(0, 1, 128)
        p[30:36] += 4.0
        profs.append(p)
    stacked, snr = stack_profiles(profs)
    print(f"  SNR mỗi đêm ≈ 3.9 → SNR gộp = {snr:.1f} (kỳ vọng ≈ 7.8)")
