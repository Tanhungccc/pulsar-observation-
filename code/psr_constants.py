# -*- coding: utf-8 -*-
"""psr_constants.py — hằng số vật lý DÙNG CHUNG (L0).

Không module nào được tự viết lại các số này. Mỗi hằng số có đơn vị và nguồn.
`self_check()` so công thức với giá trị chuẩn để bắt lỗi đơn vị.
"""
from __future__ import annotations

import math

# --- hằng số cơ bản -------------------------------------------------------
K_DM = 4.148808e3          # s · MHz^2 · pc^-1 · cm^3   (Lorimer & Kramer 2005)
C_M_S = 2.99792458e8       # m/s
K_B = 1.380649e-23         # J/K
AU_M = 1.495978707e11      # m
JY = 1e-26                 # W m^-2 Hz^-1
MJD_J2000 = 51544.5        # MJD tại J2000.0
DAY_S = 86400.0
YEAR_S = 3.15576e7
DEG = math.pi / 180.0


# --- công thức tán sắc / tán xạ ------------------------------------------
def dm_delay_s(dm: float, f_lo_mhz: float, f_hi_mhz: float) -> float:
    """Trễ tán sắc (s) giữa hai tần số. Thứ tự f_lo/f_hi không quan trọng."""
    if f_lo_mhz <= 0 or f_hi_mhz <= 0:
        raise ValueError("tần số phải > 0")
    return abs(K_DM * float(dm) * (1.0 / f_lo_mhz**2 - 1.0 / f_hi_mhz**2))


def channel_smear_ms(dm: float, chan_width_mhz: float, f_mhz: float) -> float:
    """Nhòe còn lại trong MỘT kênh sau khử tán sắc không kết hợp (ms).

    == 8.2976e6 · Δf_chan · DM / f^3  (ms), f, Δf tính bằng MHz.
    """
    f1 = f_mhz - chan_width_mhz / 2.0
    f2 = f_mhz + chan_width_mhz / 2.0
    return dm_delay_s(dm, f1, f2) * 1e3


def tau_scattering_ms(dm: float, f_mhz: float) -> float:
    """Tán xạ (ms): τ(1 GHz) ≈ 1,3e-4·(DM/100)^2,2 s (Bhat+2004), τ ∝ ν^-4,4."""
    return 1.3e-4 * (max(float(dm), 0.0) / 100.0) ** 2.2 * (f_mhz / 1000.0) ** -4.4 * 1e3


def w50_at(w50_1400_ms: float, dm: float, f_mhz: float,
           alpha_w: float = 0.3) -> float:
    """W50 tại tần số quan sát = giãn nội tại (∝ν^-α) ⊕ tán xạ (cộng bình phương)."""
    w_int = w50_1400_ms * (1400.0 / f_mhz) ** alpha_w
    return math.hypot(w_int, tau_scattering_ms(dm, f_mhz))


# --- hình học chùm tia / độ nhạy -----------------------------------------
def hpbw_deg(diameter_m: float, f_mhz: float, k: float = 1.22) -> float:
    """HPBW (độ) ≈ k·λ/D. 3,7 m @423 MHz → 13,4°; @1450 MHz → 3,83°."""
    if diameter_m <= 0 or f_mhz <= 0:
        raise ValueError("D và f phải > 0")
    lam = C_M_S / (f_mhz * 1e6)
    return k * lam / diameter_m / DEG


def gain_k_per_jy(a_eff_m2: float) -> float:
    """G (K/Jy) = A_eff/(2k). 5,91 m² → 2,14 mK/Jy."""
    return a_eff_m2 * JY / (2.0 * K_B)


def sefd_jy(tsys_k: float, a_eff_m2: float) -> float:
    """SEFD (Jy) = 2k·T_sys/A_eff. 150 K & 5,91 m² → 70 kJy."""
    return 2.0 * K_B * tsys_k / (a_eff_m2 * JY)


def self_check() -> list:
    """Trả về danh sách lỗi (rỗng = đúng). So với giá trị chuẩn đã biết."""
    bad = []
    # 1) trễ tán sắc: 1 đơn vị DM tại 1,4 GHz trên 1 MHz ≈ 3,03 µs
    d = dm_delay_s(1.0, 1399.5, 1400.5)
    if abs(d - 3.03e-6) > 0.05e-6:
        bad.append(f"dm_delay_s(1, 1399.5, 1400.5) = {d:.3e} s, cần 3.03e-6")
    # 2) nhòe nội kênh: 423 MHz, 20 MHz/64 kênh, DM 50 → 1.71 ms
    s = channel_smear_ms(50, 20.0 / 64, 423.0)
    if abs(s - 1.71) > 0.05:
        bad.append(f"channel_smear_ms = {s:.2f} ms, cần 1.71")
    # 3) HPBW: 3.7 m @423 MHz → 13.4°; @1450 MHz → 3.83°
    h1, h2 = hpbw_deg(3.7, 423.0), hpbw_deg(3.7, 1450.0)
    if abs(h1 - 13.4) > 0.2:
        bad.append(f"hpbw@423 = {h1:.2f}°, cần 13.4")
    if abs(h2 - 3.83) > 0.1:
        bad.append(f"hpbw@1450 = {h2:.2f}°, cần 3.83")
    # 4) G và SEFD: 5.91 m² → 2.14 mK/Jy; T_sys 150 K → 70 kJy
    g = gain_k_per_jy(5.91)
    if abs(g - 2.14e-3) > 0.05e-3:
        bad.append(f"gain = {g:.3e} K/Jy, cần 2.14e-3")
    sf = sefd_jy(150.0, 5.91)
    if abs(sf - 70e3) / 70e3 > 0.02:
        bad.append(f"sefd = {sf:.0f} Jy, cần 70000")
    # 5) tán xạ: B1641-45 (DM 479) tại 423 MHz ≈ 180 ms
    t = tau_scattering_ms(478.7, 423.0)
    if not (120 < t < 260):
        bad.append(f"tau_sc(479, 423) = {t:.0f} ms, kỳ vọng ~180")
    return bad
