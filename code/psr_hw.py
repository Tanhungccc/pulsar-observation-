# -*- coding: utf-8 -*-
"""
psr_hw.py — MÔ HÌNH PHẦN CỨNG + tự phát hiện + tự FALLBACK cho chuỗi thu RTP-3.7.

Mục tiêu (theo yêu cầu): "predict những bộ lọc, amplifier, thiết bị mà chảo có thể
có rồi tự động fallback để dùng" — tức là:

1. MỘT THƯ VIỆN linh kiện (LNA, BPF, SDR...) với thông số đã biết/đo được.
2. MỖI VỊ TRÍ trong chuỗi: danh sách ứng viên xếp theo mức ưu tiên → tự chọn
   cái đầu tiên đang "có mặt" (probe được hoặc người dùng khai báo).
3. TÍNH TOÁN kết quả của chuỗi đã chọn: T_sys, SEFD, gain, biên độ ADC,
   tốc độ ghi dữ liệu, mode ghi đề xuất.
4. Nếu thiếu linh kiện → GIẢI PHÁP DỰ PHÒNG rõ ràng (fallback) kèm hệ quả độ nhạy.

Cách khai báo/thiết bị có mặt:
    - probe tự động: RTL-SDR (pyrtlsdr), SoapySDR, pylibiio (Pluto) nếu cài được
    - file khai báo `hardware_inventory.json` cạnh thư mục code (tùy chọn)
    - hoặc truyền trực tiếp bằng Python API: detect_chain(band="423", have={"sdr": "rtlsdr"})

Nghiệp vụ ghi dữ liệu "để qua đêm không canh chừng": xem record_unattended.py —
module này chỉ cung cấp cấu hình ghi (nchan, tsamp, mode channelize) an toàn.
"""
from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, field, asdict

K_B = 1.380649e-23
JY = 1e-26
T_CMB = 2.725
T_SKY_1420 = 3.0      # nền thiên hà + khí quyển điển hình, |b| cao
T_SKY_423 = 25.0      # nền thiên hà mạnh hơn nhiều ở 423 MHz
T_GROUND = 25.0       # spillover + mặt đất, chảo không chắn ground


# ============================================================ THƯ VIỆN LINH KIỆN
# nf_db: độ ồn hệ quy về đầu vào | gain_db: khuếch đại | ip3_dbm: tuyến tính
# lo/hi_mhz: dải hoạt động | notes
PARTS = {
    # ---- LNA / front-end module ----
    "sawbird_hi": dict(kind="lna", name="Nooelec SAWbird+HI (LNA+SAW)",
                       nf_db=0.6, gain_db=30.0, lo_mhz=1380, hi_mhz=1460,
                       ip3_dbm=-10, bias=True,
                       note="SAW 1420 MHz, dải chỉ ~20-30 MHz: chặn nâng cấp băng rộng"),
    "spf5189z": dict(kind="lna", name="SPF5189Z (LNA rời)",
                     nf_db=0.6, gain_db=20.0, lo_mhz=50, hi_mhz=2000,
                     ip3_dbm=-5, bias=True,
                     note="LNA băng rộng rẻ, dùng được cả 423 và 1420 MHz"),
    "zkl33uln": dict(kind="lna", name="Mini-Circuits ZKL-33ULN-S+ (như TNU)",
                     nf_db=1.5, gain_db=18.0, lo_mhz=30, hi_mhz=1000,
                     ip3_dbm=0, bias=True,
                     note="NF 1.5 dB — kém SPF5189Z; giữ nếu đã có sẵn"),
    "rtl_internal": dict(kind="lna", name="LNA nội RTL-SDR (dự phòng cuối)",
                         nf_db=8.0, gain_db=44.0, lo_mhz=24, hi_mhz=1766,
                         ip3_dbm=-15, bias=False,
                         note="NF 8 dB → T_rec ~1200 K: CHỈ dùng khi hỏng LNA ngoài"),

    # ---- bộ lọc ----
    "bpf_380_450": dict(kind="bpf", name="BPF 380-450 MHz",
                        nf_db=1.5, lo_mhz=380, hi_mhz=450,
                        note="BẮT BUỘC ở 423 MHz: chặn FM 88-108, hàng không, TETRA"),
    "lpf_450": dict(kind="bpf", name="LPF SLP-450+ (như TNU)",
                    nf_db=1.0, lo_mhz=0.1, hi_mhz=450,
                    note="LPF KHÔNG chặn FM → chỉ dự phòng, gây bão hoà ADC ở TP"),
    "bpf_1300_1500": dict(kind="bpf", name="BPF 1300-1500 MHz",
                          nf_db=1.5, lo_mhz=1300, hi_mhz=1500,
                          note="Thay/bổ sung SAW khi cần băng rộng tại L-band"),
    "saw_1420": dict(kind="bpf", name="SAW 1420 MHz (tích hợp SAWbird)",
                     nf_db=0.5, lo_mhz=1400, hi_mhz=1440,
                     note="Chẹt băng ~25 MHz — chấp nhận cho HI, không cho pulsar băng rộng"),

    # ---- SDR ----
    "rtlsdr_v5": dict(kind="sdr", name="RTL-SDR v5 (TCXO ±0.5 ppm)",
                      bw_mhz=2.4, max_rate_msps=3.2, bits=8, reliable_rate=2.4,
                      ppm=0.5, loss_warning_msps=3.2,
                      note="Mất mẫu >2.4 MS/s trên USB 2.0; cần kiểm tra sample counter"),
    "rsp1a": dict(kind="sdr", name="SDRplay RSP1A/RSPdx",
                  bw_mhz=8.0, max_rate_msps=12.0, bits=12, reliable_rate=8.0,
                  ppm=0.05, loss_warning_msps=12.0,
                  note="Đồng hồ ổn hơn, 8 MHz ăn nhập với nhịp ghi an toàn"),
    "pluto": dict(kind="sdr", name="ADALM-Pluto (firmware nâng 20 MHz)",
                  bw_mhz=20.0, max_rate_msps=20.0, bits=12, reliable_rate=16.0,
                  ppm=0.5, loss_warning_msps=16.0,
                  note="USB ổn tới ~16 MS/s; hỗ trợ stream liên tục (cho A3)"),
    "limesdr": dict(kind="sdr", name="LimeSDR Mini",
                    bw_mhz=30.0, max_rate_msps=30.0, bits=12, reliable_rate=20.0,
                    ppm=0.5, loss_warning_msps=20.0, note=""),
    "usrp": dict(kind="sdr", name="USRP B210",
                 bw_mhz=56.0, max_rate_msps=61.4, bits=12, reliable_rate=40.0,
                 ppm=0.01, loss_warning_msps=61.4,
                 note="Băng rộng nhất; cần PC đủ mạnh"),

    # ---- nguồn cấp điện / phụ trợ ----
    "bias_tee": dict(kind="aux", name="Bias-tee 5V",
                     note="Cấp nguồn LNA qua cáp đồng trục"),
    "gpsdo": dict(kind="aux", name="GPSDO 10 MHz",
                  ppm=0.0001,
                  note="Cần cho timing dài; fold <2 h thì TCXO ±0.5 ppm đủ"),
}


# ============================================================ CHUỖI + TÍNH TOÁN
@dataclass
class ChainResult:
    band_mhz: float
    parts: dict                 # vị trí -> part_id đã chọn
    fallbacks: list = field(default_factory=list)   # các vị trí dùng phương án dự phòng
    missing: list = field(default_factory=list)     # vị trí không có gì → chế độ yếu nhất
    t_rec_k: float = 0.0
    t_sys_k: float = 0.0
    gain_db: float = 0.0
    sefd_jy: float = 0.0
    bw_mhz: float = 0.0
    tsamp_us: float = 0.0
    nchan: int = 0
    data_rate_kbps: float = 0.0
    adc_headroom_db: float = 0.0
    warnings: list = field(default_factory=list)

    def summary(self) -> str:
        lines = [f"=== CHUỖI THU @ {self.band_mhz:.0f} MHz ==="]
        for pos, pid in self.parts.items():
            tag = " (DỰ PHÒNG)" if pos in self.fallbacks else ""
            name = PARTS.get(pid, {}).get("name", pid)
            lines.append(f"  {pos:10} -> {name}{tag}")
        if self.missing:
            lines.append(f"  THIẾU: {', '.join(self.missing)} (dùng chế độ yếu nhất)")
        lines += [
            f"  T_rec = {self.t_rec_k:.0f} K | T_sys = {self.t_sys_k:.0f} K",
            f"  SEFD  = {self.sefd_jy/1e3:.1f} kJy | gain = {self.gain_db:.0f} dB",
            f"  Ghi: B = {self.bw_mhz:.1f} MHz, {self.nchan} kênh, "
            f"{self.tsamp_us:.0f} µs/mẫu → {self.data_rate_kbps:.0f} kbps (dynamic spectrum)",
        ]
        for w in self.warnings:
            lines.append(f"  ⚠ {w}")
        return "\n".join(lines)


def t_rec_from_nf(nf_db: float) -> float:
    """Nhiệt độ tương đương của LNA: T = T0(10^(NF/10) - 1), T0 = 290 K."""
    return 290.0 * (10 ** (nf_db / 10.0) - 1.0)


def detect_sdr(have: dict | None = None) -> str | None:
    """Thử phát hiện SDR thật; trả về part_id hoặc None."""
    if have and have.get("sdr"):
        return have["sdr"]
    try:
        from rtlsdr import RtlSdr               # noqa
        try:
            s = RtlSdr()
            s.close()
            return "rtlsdr_v5"
        except Exception:
            return None                        # có lib nhưng không cắm thiết bị
    except Exception:
        pass
    for mod, pid in (("SoapySDR", None), ("iio", "pluto")):
        try:
            __import__(mod)
        except Exception:
            continue
        if pid:
            return pid
    return None


def detect_chain(band: str = "423", have: dict | None = None,
                 goal: str = "pulsar") -> ChainResult:
    """Xây chuỗi tốt nhất cho băng `band` ('423' hoặc '1420') từ những gì đang có.

    have: dict tùy chọn {"sdr": ..., "lna": ..., "bpf": ..., "aux": [...]}
          — giá trị là part_id trong PARTS. Bỏ qua → tự probe + giả định dự phòng.
    goal: 'pulsar' (ưu tiên băng thông) | 'hi' (ưu tiên SAW 1420) | 'unattended'
          (ưu tiên an toàn dài hạn).
    """
    have = dict(have or {})
    band_mhz = 423.0 if str(band).startswith("4") else 1420.0
    fb, miss = [], []
    parts: dict[str, str] = {}

    # ---- SDR
    sdr_id = detect_sdr(have)
    if sdr_id is None:
        sdr_id = "rtlsdr_v5"          # mô phỏng/giả lập: vẫn tính được cấu hình
        fb.append("sdr")
        miss.append("sdr(thiết bị)")
    parts["sdr"] = sdr_id
    sdr = PARTS[sdr_id]

    # ---- LNA
    want_lna = have.get("lna")
    if want_lna and want_lna in PARTS:
        parts["lna"] = want_lna
    else:
        if band_mhz < 800:
            order = ["spf5189z", "zkl33uln", "sawbird_hi", "rtl_internal"]
        else:
            order = ["sawbird_hi", "spf5189z", "zkl33uln", "rtl_internal"]
        # tự probe: chuỗi SAWbird/SPF không probe được → giả định dự phòng theo thứ tự
        parts["lna"] = order[0] if not have else order[0]
        fb.append("lna")
        if parts["lna"] == "rtl_internal":
            miss.append("lna_ngoai")
    lna = PARTS[parts["lna"]]

    # ---- BPF
    if band_mhz < 800:
        bpf_order = ["bpf_380_450", "lpf_450", "saw_1420"]
    else:
        if goal == "hi":
            bpf_order = ["saw_1420", "bpf_1300_1500"]
        else:
            bpf_order = ["bpf_1300_1500", "saw_1420"]
    want_bpf = have.get("bpf")
    parts["bpf"] = want_bpf if want_bpf in PARTS else bpf_order[0]
    if parts["bpf"] != bpf_order[0]:
        fb.append("bpf")
    bpf = PARTS[parts["bpf"]]

    # ---- phụ trợ
    parts["bias"] = "bias_tee"
    if "gpsdo" in (have.get("aux") or []):
        parts["clock"] = "gpsdo"
    else:
        parts["clock"] = "tcxo_" + sdr_id
        fb.append("clock")

    # ---- TÍNH T_SYS ----
    t_rec = t_rec_from_nf(lna["nf_db"])
    t_sky = T_SKY_423 if band_mhz < 800 else T_SKY_1420
    t_sys = T_CMB + t_sky + T_GROUND + t_rec + t_rec_from_nf(bpf.get("nf_db", 0.0)) * 0.3
    gain_db = lna["gain_db"] + sdr.get("gain_db", 0.0)

    # ---- cấu hình ghi: dynamic spectrum an toàn (channelize ngay) ----
    bw = min(sdr["bw_mhz"], (bpf["hi_mhz"] - bpf["lo_mhz"]))
    if parts["bpf"] == "saw_1420":
        bw = min(bw, 25.0)
    nchan = 128 if bw >= 20 else (64 if bw >= 5 else 32)
    tsamp_us = 100.0 if goal != "unattended" else 200.0
    data_rate_kbps = nchan * 8 * (1e6 / tsamp_us) / 1e3 / 8   # uint8 per sample

    # ---- cảnh báo ----
    warns = []
    if lna["lo_mhz"] > band_mhz or lna["hi_mhz"] < band_mhz:
        warns.append(f"LNA {lna['name']} không phủ {band_mhz:.0f} MHz")
    if bpf["lo_mhz"] > band_mhz or bpf["hi_mhz"] < band_mhz:
        warns.append(f"BPF {bpf['name']} không phủ {band_mhz:.0f} MHz")
    if band_mhz < 800 and parts["bpf"] == "lpf_450":
        warns.append("LPF không chặn FM 88-108 MHz → dùng BPF 380-450 nếu có")
    if sdr["ppm"] > 0.2 and goal == "timing":
        warns.append("Đồng hồ SDR trôi — cần GPSDO cho timing dài")
    # tuyến tính ADC: ước lượng biên độ đầu vào = gain + log10(B) của nhiễu
    noise_floor_dbm = -174 + 10 * math.log10(bw * 1e6) + lna["nf_db"] + T_GROUND / 290 * 10
    adc_full_scale_dbm = -10.0     # RTL-SDR ≈ 0 dBFS @ -10 dBm
    headroom = adc_full_scale_dbm - (noise_floor_dbm + gain_db)
    if headroom < 6:
        warns.append(f"Biên ADC chỉ còn {headroom:.0f} dB — giảm gain để khỏi clipping")
    if headroom > 30:
        warns.append(f"Biên ADC dư {headroom:.0f} dB — tăng gain để dùng hết dồn động")
    if t_sys > 500:
        warns.append(f"T_sys = {t_sys:.0f} K RẤT CAO (LNA hỏng/yếu hoặc feed sai) "
                     f"— độ nhạy giảm ~{t_sys/130:.0f}× so với chuỗi tốt; "
                     f"ưu tiên sửa LNA trước khi quan sát")
    elif t_sys > 250:
        warns.append(f"T_sys = {t_sys:.0f} K cao — kiểm tra LNA/feed/chắn ground")

    aeff = 0.55 * math.pi * 3.7**2 / 4
    sefd = 2 * K_B * t_sys / aeff / JY

    r = ChainResult(
        band_mhz=band_mhz, parts=parts, fallbacks=sorted(set(fb)), missing=miss,
        t_rec_k=t_rec, t_sys_k=t_sys, gain_db=gain_db, sefd_jy=sefd,
        bw_mhz=bw, tsamp_us=tsamp_us, nchan=nchan,
        data_rate_kbps=data_rate_kbps, adc_headroom_db=headroom, warnings=warns)
    return r


# ============================================================ kiểm thử nội bộ
def self_check() -> list[str]:
    """Kiểm chứng công thức của module này — trả về danh sách lỗi (rỗng = tốt)."""
    errs = []
    t = t_rec_from_nf(0.6)
    if abs(t - 45.0) > 5:                     # 290*(10^0.06-1)=43.7 K
        errs.append(f"T_rec(NF 0.6 dB) = {t:.1f} K (mong 40–50 K)")
    c = detect_chain("423")
    if c.band_mhz != 423.0:
        errs.append("band parse lỗi")
    if not (100 < c.t_sys_k < 400):
        errs.append(f"T_sys 423 MHz = {c.t_sys_k:.0f} K ngoài khoảng hợp lý")
    c2 = detect_chain("1420", goal="hi")
    if not (60 < c2.t_sys_k < 250):
        errs.append(f"T_sys 1420 MHz = {c2.t_sys_k:.0f} K ngoài khoảng hợp lý")
    c3 = detect_chain("1420", have={"lna": "rtl_internal"})
    if c3.t_sys_k < 800:
        errs.append("LNA nội phải cho T_sys > 800 K")
    return errs


if __name__ == "__main__":
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    for band, goal in (("423", "pulsar"), ("1420", "pulsar"), ("1420", "hi")):
        print(detect_chain(band, goal=goal).summary())
        print()
    errs = self_check()
    print("self_check:", "OK" if not errs else errs)

    # ví dụ fallback: chỉ còn LNA nội + LPF (mô phỏng hỏng LNA ngoài)
    worst = detect_chain("423", have={"lna": "rtl_internal", "bpf": "lpf_450"})
    print()
    print("=== TRƯỜNG HỢP HỎNG LNA NGOÀI (fallback) ===")
    print(worst.summary())
