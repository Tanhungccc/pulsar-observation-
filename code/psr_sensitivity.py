# -*- coding: utf-8 -*-
"""
psr_sensitivity.py — Ngân sách S/N (link budget) của kính POAM RTP-3.7 cho pulsar.

Toàn bộ con số trong docs/02 đều lấy từ file này. Chạy:

    python psr_sensitivity.py            # bảng cấu hình × mục tiêu
    python psr_sensitivity.py --check    # đối chiếu với PROJECT_PLAN.md

Công thức (Lorimer & Kramer 2005, ch.7):
    A_eff      = eta * pi * D^2 / 4                      [m^2]
    SEFD       = 2 k Tsys / A_eff                        [Jy]
    G          = A_eff * 1e-26 / (2 k)                   [K/Jy]
    SNR_fold   = (S_peak / SEFD) * sqrt(n_pol B t) * sqrt(W/(P-W))
      với S_peak = S_mean * P/W  (thông lượng ĐỈNH trong xung)
    => SNR_fold = (S_mean / SEFD) * sqrt(n_pol B t) * sqrt(P/W)
    SNR_single = (S_pulse / SEFD) * sqrt(n_pol B W_pulse)  (một xung đơn)
"""
from __future__ import annotations

import argparse
import math
from dataclasses import dataclass

from psr_core import ensure_utf8_stdout

K_B = 1.380649e-23        # J/K
JY = 1e-26                # W m^-2 Hz^-1
C_KMS = 299792.458
K_DM = 4.148808e3         # s * MHz^2


@dataclass
class Dish:
    D_m: float = 3.7
    eta: float = 0.55

    @property
    def area_m2(self) -> float:
        return math.pi * self.D_m ** 2 / 4.0

    @property
    def aeff_m2(self) -> float:
        return self.eta * self.area_m2

    def beam_deg(self, f_mhz: float) -> float:
        """HPBW xấp xỉ cho chảo parabol chiếu đều: 1.22 lambda/D (độ)."""
        lam = 299.792458 / f_mhz                      # m
        return math.degrees(1.22 * lam / self.D_m)

    def gain_kjy(self) -> float:
        return self.aeff_m2 * JY / (2 * K_B)

    def sefd_jy(self, tsys_k: float) -> float:
        return 2 * K_B * tsys_k / self.aeff_m2 / JY


@dataclass
class Config:
    """Một cấu hình thu nhận cụ thể (SDR + front-end)."""
    name: str
    f_mhz: float
    bw_mhz: float
    tsys_k: float
    nchan: int
    tsamp_us: float
    n_pol: int = 1

    @property
    def chan_width_mhz(self) -> float:
        return self.bw_mhz / self.nchan


# --------------------------------------------------------------- hiệu ứng DM
def band_smear_ms(dm: float, bw_mhz: float, f_mhz: float) -> float:
    """Trải xung trên toàn dải khi KHÔNG khử tán sắc."""
    f1, f2 = f_mhz - bw_mhz / 2, f_mhz + bw_mhz / 2
    return abs(K_DM * dm * (1 / f1**2 - 1 / f2**2)) * 1e3


def chan_smear_ms(dm: float, chan_width_mhz: float, f_mhz: float) -> float:
    """Trải còn lại trong 1 kênh sau khử tán sắc không kết hợp."""
    f1, f2 = f_mhz - chan_width_mhz / 2, f_mhz + chan_width_mhz / 2
    return abs(K_DM * dm * (1 / f1**2 - 1 / f2**2)) * 1e3


# ------------------------------------------------------------------ SNR
def snr_fold(s_mean_jy: float, sefd_jy: float, bw_hz: float, t_s: float,
             period_s: float, w_s: float, n_pol: int = 1) -> float:
    """SNR của hồ sơ xung sau khi fold. S_mean = thông lượng trung bình (mJy→Jy)."""
    duty = min(max(w_s / period_s, 1e-5), 0.95)
    return (s_mean_jy / sefd_jy) * math.sqrt(n_pol * bw_hz * t_s) \
        * math.sqrt((1 - duty) / duty)


def snr_single(s_peak_jy: float, sefd_jy: float, bw_hz: float,
               w_s: float, n_pol: int = 1) -> float:
    """SNR của MỘT xung (giant pulse / single pulse)."""
    return (s_peak_jy / sefd_jy) * math.sqrt(n_pol * bw_hz * w_s)


def required_time_s(target_snr: float, s_mean_jy: float, sefd_jy: float,
                    bw_hz: float, period_s: float, w_s: float,
                    n_pol: int = 1) -> float:
    duty = min(max(w_s / period_s, 1e-5), 0.95)
    k = (s_mean_jy / sefd_jy) * math.sqrt((1 - duty) / duty)
    if k <= 0:
        return float("inf")
    return (target_snr / k) ** 2 / bw_hz


def verdict(snr: float, t_s: float) -> str:
    if snr >= 12:
        return "KHẢ THI"
    if snr >= 6:
        return "CHỜ ĐƯỢC (cần xác nhận)"
    if snr >= 3:
        return "RẤT KHÓ (biên)"
    return "KHÔNG KHẢ THI"


# ------------------------------------------------------------------ bảng
if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="doi chieu SEFD voi PROJECT_PLAN.md")
    args = ap.parse_args()
    ensure_utf8_stdout()

    dish = Dish()
    print(f"RTP-3.7: A_geom = {dish.area_m2:.2f} m2, "
          f"A_eff = {dish.aeff_m2:.2f} m2 (eta={dish.eta})")
    print(f"G = {dish.gain_kjy()*1e3:.3f} mK/Jy")
    for f in (1420.0, 408.0):
        print(f"  {f:7.0f} MHz: beam = {dish.beam_deg(f):5.2f} deg, "
              f"SEFD(Tsys=100K) = {dish.sefd_jy(100)/1e3:9.1f} kJy, "
              f"SEFD(Tsys=150K) = {dish.sefd_jy(150)/1e3:9.1f} kJy")

    if args.check:
        print("\n--- Đối chiếu PROJECT_PLAN.md §1 ---")
        for tsys in (150, 250):
            print(f"  Tsys={tsys} K @1420 MHz: SEFD thật = "
                  f"{dish.sefd_jy(tsys):.0f} Jy  (PROJECT_PLAN ghi 250/410 Jy)")
        print("  => Số trong PROJECT_PLAN nhỏ hơn thực tế ~280 lần "
              "(hệ quả: SNR pulsar bị ước lượng cao ~280x)")
