# -*- coding: utf-8 -*-
"""psr_site.py — HỒ SƠ TRẠM & KÍNH (L0).

Mục đích: **không viết cứng** toạ độ trạm hay thông số chảo trong code. Mọi module
khác lấy từ `active_profile()`:
    psr_site.LAT_DEG, LON_DEG, TZ_H          (tương thích code cũ)
    psr_site.active_profile().site / .telescope / .band("lband")

Quy ước:
- HPBW = 1,22·λ/D; G = A_eff/(2k); SEFD = 2k·T_sys/A_eff (xem `psr_constants`).
- `Band.eff` cho phép ghi đè hiệu suất theo băng (mặt chảo 8 tấm đạt ~0,70 ở L-band
  theo G/T đo được của RTP37, nhưng chỉ ~0,55 ở 423 MHz do tràn chùm tia).
- Hồ sơ lưu dạng JSON; `PSR_PROFILE` (đường dẫn) để dùng hồ sơ khác khi kiểm thử.
"""
from __future__ import annotations

import json
import math
import os
import sys
from dataclasses import dataclass, field, asdict

import psr_constants as K


@dataclass
class Site:
    name: str = "TP.HCM"
    lat_deg: float = 10.7769
    lon_deg: float = 106.7009
    elev_m: float = 10.0
    tz_offset_h: float = 7.0

    @property
    def lat_rad(self) -> float:
        return math.radians(self.lat_deg)


@dataclass
class Telescope:
    name: str = "POAM RTP-3.7"
    diameter_m: float = 3.7
    efficiency: float = 0.55
    mount: str = "track"          # track | fixed
    hpbw_k: float = 1.22          # HPBW = k·λ/D; RTP37 đo được k ≈ 1,20

    def area_m2(self) -> float:
        return math.pi * (self.diameter_m / 2.0) ** 2

    def a_eff_m2(self, eff: float | None = None) -> float:
        return (eff if eff is not None else self.efficiency) * self.area_m2()

    def gain_k_per_jy(self, eff: float | None = None) -> float:
        return K.gain_k_per_jy(self.a_eff_m2(eff))

    def hpbw_deg(self, f_mhz: float) -> float:
        return K.hpbw_deg(self.diameter_m, f_mhz, k=self.hpbw_k)


@dataclass
class Band:
    id: str
    fc_mhz: float
    bw_mhz: float
    tsys_k: float = 150.0
    eff: float | None = None       # ghi đè hiệu suất riêng cho băng này
    note: str = ""

    def sefd_jy(self, tel: Telescope) -> float:
        return K.sefd_jy(self.tsys_k, tel.a_eff_m2(self.eff))

    def gain_k_per_jy(self, tel: Telescope) -> float:
        return tel.gain_k_per_jy(self.eff)

    def hpbw_deg(self, tel: Telescope) -> float:
        return tel.hpbw_deg(self.fc_mhz)


@dataclass
class Profile:
    id: str = "poam-rtp37-hcmc"
    site: Site = field(default_factory=Site)
    telescope: Telescope = field(default_factory=lambda: Telescope(hpbw_k=1.20))
    bands: list = field(default_factory=lambda: [
        Band("lband", 1420.0, 50.0, 97.5, 0.70, "L-band 1350–1450, G/T 13,55 dB/K"),
        Band("p423", 423.0, 20.0, 150.0, 0.55, "cần feed+LNA+BPF 380–450 MHz"),
    ])
    backend: dict = field(default_factory=lambda: {
        "type": "N6002", "max_bw_mhz": 50.0, "bits": 8, "channels": 2})
    rfi: dict = field(default_factory=lambda: {
        "notch_mhz": [[88, 108]], "notes": "FM rất mạnh ở TP.HCM"})
    schema_version: int = 1

    # --- tra băng -------------------------------------------------------
    def band(self, key: str | float) -> Band | None:
        """Tra theo id ('lband') hoặc theo tần số (MHz) gần nhất trong ±10 %."""
        if isinstance(key, str):
            for b in self.bands:
                if b.id.lower() == key.lower():
                    return b
            return None
        for b in self.bands:
            if abs(b.fc_mhz - float(key)) <= 0.10 * b.fc_mhz:
                return b
        return None

    # --- kiểm tra chia kênh --------------------------------------------
    def check_channelization(self, band: Band, nchan: int, dm: float,
                             w50_ms: float) -> dict:
        """Cảnh báo nếu nhòe trong kênh vượt 50 % W50 (mất độ nhạy)."""
        if nchan <= 0:
            return dict(ok=False, smear_ms=float("inf"),
                        advice="số kênh phải > 0")
        chan = band.bw_mhz / nchan
        smear = K.channel_smear_ms(dm, chan, band.fc_mhz)
        ok = smear <= 0.5 * max(w50_ms, 1e-6)
        need = int(math.ceil(band.bw_mhz / (2 * 0.5 * w50_ms / K.channel_smear_ms(
            dm, 1.0, band.fc_mhz)))) if dm > 0 else nchan
        advice = "" if ok else (
            f"nhòe {smear:.2f} ms > 0,5·W50 ({0.5*w50_ms:.2f} ms) → "
            f"tăng số kênh lên ≥ {max(need, nchan)} hoặc giảm băng thông")
        return dict(ok=ok, smear_ms=round(smear, 3), channel_mhz=round(chan, 4),
                    advice=advice)

    # --- I/O ------------------------------------------------------------
    def to_dict(self) -> dict:
        d = asdict(self)
        d["bands"] = [asdict(b) for b in self.bands]
        return d

    def save(self, path: str) -> str:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(self.to_dict(), fh, ensure_ascii=False, indent=2)
        return path


def app_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def profiles_dir() -> str:
    return os.environ.get("PSR_PROFILE_DIR") or os.path.join(app_dir(), "configs")


def default_profile() -> Profile:
    return Profile()


def load_profile(path: str) -> Profile:
    with open(path, encoding="utf-8") as fh:
        d = json.load(fh)
    p = Profile(id=d.get("id", "custom"))
    if "site" in d:
        p.site = Site(**d["site"])
    if "telescope" in d:
        p.telescope = Telescope(**d["telescope"])
    if "bands" in d:
        p.bands = [Band(**b) for b in d["bands"]]
    if "backend" in d:
        p.backend = d["backend"]
    if "rfi" in d:
        p.rfi = d["rfi"]
    return p


def ensure_default_profile() -> str:
    """Bảo đảm có configs/<id>.json cạnh app; thiếu thì ghi hồ sơ mặc định."""
    d = profiles_dir()
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, "{}.json".format(default_profile().id))
    if not os.path.exists(path):
        default_profile().save(path)
    return path


def active_profile() -> Profile:
    """Hồ sơ đang dùng: `PSR_PROFILE` (đường dẫn) hoặc mặc định (RTP37 @ TP.HCM)."""
    path = os.environ.get("PSR_PROFILE")
    if path and os.path.exists(path):
        try:
            return load_profile(path)
        except Exception as exc:
            print(f"⚠ không đọc được hồ sơ {path}: {exc!r} — dùng mặc định")
    return default_profile()


# --- tương thích code cũ (psr_targets dùng các tên này) -------------------
_P = active_profile()
LAT_DEG = _P.site.lat_deg
LON_DEG = _P.site.lon_deg
TZ_H = _P.site.tz_offset_h


def apply_profile(p: Profile) -> None:
    """Đổi hồ sơ đang dùng cho tiến trình hiện tại (dùng trong test)."""
    global LAT_DEG, LON_DEG, TZ_H, _P
    _P = p
    LAT_DEG, LON_DEG, TZ_H = p.site.lat_deg, p.site.lon_deg, p.site.tz_offset_h


def self_check() -> list:
    """Kiểm tra hồ sơ mặc định cho lại đúng số đã công bố."""
    bad = []
    p = default_profile()
    t = p.telescope
    if abs(t.area_m2() - 10.75) > 0.05:
        bad.append(f"diện tích {t.area_m2():.2f} m², cần 10.75")
    lb = p.band("lband")
    p423 = p.band("p423")
    if lb is None or p423 is None:
        bad.append("thiếu băng lband/p423")
        return bad
    h1 = t.hpbw_deg(1450.0)          # datasheet ghi 3,83° tại 1450 MHz
    if abs(h1 - 3.83) > 0.10:
        bad.append(f"HPBW @1450 {h1:.2f}°, cần 3.83 (datasheet)")
    h2 = p423.hpbw_deg(t)
    if abs(h2 - 13.2) > 0.3:
        bad.append(f"HPBW 423 {h2:.2f}°, cần 13.2")
    s1 = lb.sefd_jy(t) / 1e3
    if abs(s1 - 35.8) > 1.5:
        bad.append(f"SEFD lband {s1:.1f} kJy, cần 35.8")
    s2 = p423.sefd_jy(t) / 1e3
    if abs(s2 - 70.1) > 2.0:
        bad.append(f"SEFD 423 {s2:.1f} kJy, cần 70.1")
    # băng 20 MHz / 64 kênh, DM 50, W50 10 ms → phải CẢNH BÁO (nhòe 1.7 ms > 5 ms? không)
    chk = p.check_channelization(Band("x", 423.0, 20.0), 64, 50.0, 2.0)
    if chk["ok"]:
        bad.append("check_channelization không cảnh báo khi nhòe 1.71 ms > W50/2 = 1 ms")
    chk2 = p.check_channelization(p423, 256, 50.0, 25.0)
    if not chk2["ok"]:
        bad.append("check_channelization báo động sai với 256 kênh, W50 25 ms")
    return bad


if __name__ == "__main__":
    import sys as _s
    try:
        _s.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    prof = active_profile()
    print(f"Hồ sơ: {prof.id} | {prof.telescope.name} @ {prof.site.name}")
    print(f"  lat {prof.site.lat_deg}° lon {prof.site.lon_deg}° tz +{prof.site.tz_offset_h}")
    print(f"  D {prof.telescope.diameter_m} m, η {prof.telescope.efficiency}, "
          f"A_eff {prof.telescope.a_eff_m2():.2f} m²")
    for b in prof.bands:
        print(f"  băng {b.id}: {b.fc_mhz:.0f} MHz, B {b.bw_mhz:.0f} MHz, "
              f"T_sys {b.tsys_k} K → SEFD {b.sefd_jy(prof.telescope)/1e3:.1f} kJy, "
              f"HPBW {b.hpbw_deg(prof.telescope):.2f}°")
    print("self_check:", self_check() or "PASS (0 lỗi)")
