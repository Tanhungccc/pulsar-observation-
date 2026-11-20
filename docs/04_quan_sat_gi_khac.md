# 04 — Ngoài pulsar: kính 3.7 m còn quan sát được gì?

*Số liệu trong bảng lấy từ `python code/psr_targets.py --objects`.*
*Nhắc lại thang: 1 Jy → 2.14 mK nhiệt độ ăng-ten; `T_A = G·S` khi nguồn **lấp đầy**
chùm tia (nguồn điểm thì đúng tuyệt đối, nguồn nhỏ hơn chùm bị "pha loãng").*

---

## 1. Nguyên tắc: cái gì kính này làm tốt, cái gì không

**Làm tốt:**
- Nguồn **mạnh** (≳ 50 Jy) — không cần độ nhạy cao.
- Cấu trúc **rộng** (≳ 1°) — beam 4° không phải vấn đề.
- **Phổ** với độ phân giải vận tốc trung bình (2 km/s).
- Đo **biến thiên** theo thời gian (nguồn mạnh).

**Không làm được:**
- Nguồn điểm yếu (mJy) — trừ khi tích luỹ rất dài.
- Phân giải cấu trúc < 4°.
- Đo tuyệt đối chính xác (cần chuẩn hoá cẩn thận).

---

## 2. Bảng mục tiêu continuum (làm được **ngay** với thiết bị hiện có)

| Mục tiêu | Loại | `alt_max` | S (Jy) | `T_A` | Nhận xét |
|---|---|---|---|---|---|
| **Cas A** (Taurus A) | Tàn dư siêu tân tinh | 42° | 2700 | **5.8 K** | Chuẩn số 1; giảm 0.7 %/năm |
| **Cyg A** | Thiên hà vô tuyến | 60° | 1600 | 3.4 K | Chuẩn số 2, có "hot spot" |
| **Tau A** (tinh vân Cua) | Tinh vân pulsar | 79° | 1000 | 2.1 K | Cùng hướng pulsar Cua |
| **Sgr A** (tâm Ngân Hà) | Vùng trung tâm | 50° | 1500 | 3.2 K | Nguồn rộng, trộn nhiều thứ |
| **Orion A** (M42) | Vùng HII | 74° | 400 | 0.86 K | Có vạch tái hợp H, OH maser |
| **Vir A** (M87) | Thiên hà elip + jet | 88° | 210 | 0.45 K | Gần thiên đỉnh |
| **M31** (Tiên Nữ) | Thiên hà xoắn ốc | 60° | ~120 | 0.26 K | Cần dải vận tốc ±400 km/s |
| **M33** (Tam Giác) | Thiên hà xoắn ốc | 70° | ~60 | 0.13 K | Gần thiên đỉnh (89° khi qua trung tuyến) |
| **3C 273** | Quasar | 81° | 15 | 32 mK | Biến quang; cần tích luỹ |
| **Mặt Trăng** | Vật thể hệ Mặt Trời | — | ~1300 | **3.4 K** | `T_B ≈ 220 K`, đường kính 0.5° → pha loãng 1/64; chuẩn beam rất tốt |
| **Mặt Trời** (yên tĩnh) | Sao | — | ~4×10⁵ | ~13 K | Pha loãng 1/64; **nguy hiểm khi có bão** — xem §6 |

### Ba thí nghiệm continuum đáng làm nhất

**(a) HI **hấp thụ** về phía Cas A** — thí nghiệm kinh điển, rất phù hợp chảo nhỏ.
Cas A cho nền continuum 5.8 K; khí HI lạnh nằm giữa ta và Cas A **hấp thụ** vạch 21 cm
→ phổ **ngược** (dip) thay vì đỉnh. Đo được `N_HI` và nhiệt độ spin của các đám mây
lạnh trên đường nhìn. Chỉ cần: trỏ Cas A, tích luỹ 10–30 phút, phổ 256 kênh. Đây là
kết quả khoa học **chắc chắn** và bổ sung trực tiếp cho chương trình HI.

**(b) Đo suy giảm thông lượng Cas A** (0.7 %/năm) — cần thang hiệu chuẩn ổn định
nhiều năm và nguồn so sánh (Cyg A). Là dự án **nhiều năm**, giá trị cao vì dữ liệu
nghiệp dư dài hạn rất hiếm.

**(c) Biến quang 3C 273** — 15 Jy, cần SNR ~20 → 1 h ở 2.4 MHz cho `T_A = 32 mK` với
`ΔT = 1.6 mK` → SNR ≈ 20. Đủ để theo dõi biến thiên tuần/tháng.

---

## 3. Vạch phổ — ngoài HI 21 cm còn gì?

| Vạch | Tần số (MHz) | Trong dải 1300–1500? | `T_A` điển hình | Ghi chú |
|---|---|---|---|---|
| **HI 21 cm** | 1420.406 | ✅ | 20–80 K (Ngân Hà) | Chương trình chính, đã có |
| **H166α** (tái hợp hydro) | **1424.734** | ✅ **ngay cạnh HI** | 0.05–0.5 K | Hướng Orion A, W3, Sgr B2; cần kênh ≤ 50 kHz |
| OH 1612.231 (maser) | 1612.231 | ❌ (ngoài SAW) | tới vài chục Jy | Cần SDR băng rộng + BPF mới |
| OH 1665.401 / 1667.359 | 1665/1667 | ❌ | vài Jy | Như trên |
| OH 1720.530 | 1720.530 | ❌ | vài Jy | Như trên |
| Methanol 6668.519 | 6668.5 | ❌ | — | Ngoài khả năng |

**H166α là "món quà"**: nó nằm **4.3 MHz trên vạch HI**, hoàn toàn trong dải của
SAWbird+HI. Với 64 kênh/2.4 MHz (37.5 kHz/kênh ≈ 8 km/s) ta có thể thử tìm vạch này
hướng Orion A. Độ nhạy: `ΔT = 150 K/√(B·τ)` → 13 mK cho 1 h với 37.5 kHz → vạch
50–100 mK cho SNR 4–8. **Đây là mục tiêu "bonus" hợp lý**, nhưng phải tách cẩn thận
khỏi cấu trúc bandpass.

**HVC (High-Velocity Clouds)** — mây hydro vận tốc cao (`v_LSR` từ −100 đến −400 km/s).
Trong dải ±250 km/s của RTL-SDR, các HVC như **Complex C** (hướng `l ≈ 90°`, `b ≈ 40°`)
là mục tiêu thực tế: chúng là khí **bên ngoài đĩa Ngân Hà**, giá trị khoa học cao hơn
một đỉnh HI thông thường. Không cần thêm thiết bị — chỉ cần trỏ đúng và tích luỹ.

---

## 4. Bảng ưu tiên (theo "làm được ngay" → "cần nâng cấp")

### Làm ngay với thiết bị hiện có (2.4 MHz, 1.4 GHz)

| # | Mục tiêu | Thời gian | Kết quả |
|---|---|---|---|
| 1 | Khảo sát RFI 24 h + đo `T_sys` (Y-factor trên Cas A) | 3–5 ngày | Nền tảng cho MỌI quan sát |
| 2 | Drift scan Mặt Trăng + Cas A → beam, pointing model | 1 buổi | Sửa sai số trỏ, hiệu chuẩn |
| 3 | **HI hấp thụ về phía Cas A** | 1–2 buổi | Phổ hấp thụ, `N_HI`, khí lạnh |
| 4 | Bản đồ HI Ngân Hà (chương trình chính, đã có) | 2–3 tháng | (đã có trong `PROJECT_PLAN`) |
| 5 | Photometry: Cyg A, Tau A, Vir A, Orion A, 3C 273 | 1–2 tháng | Thang thông lượng, biến quang |
| 6 | Tìm **HVC** (Complex C, `l≈90`) | 2–3 buổi | Khí ngoài đĩa — kết quả mới |
| 7 | Thử **H166α** hướng Orion A / W3 | 2–3 buổi | Vạch tái hợp (khó, "bonus") |
| 8 | SETI băng hẹp (dùng lại dữ liệu HI, `t_drift` search) | miễn phí | Không tốn thêm thời gian quan sát |

### Cần nâng cấp thiết bị

| Mục tiêu | Cần gì | Chi phí tương đối |
|---|---|---|
| **Pulsar** (chương trình này) | SDR 10–40 MHz + bỏ SAW + BPF | ⭐⭐⭐ |
| M31 / M33 phổ HI hai đỉnh | dải ±400 km/s (SDR 10 MHz) | ⭐⭐ |
| OH maser 1612/1665/1667 | SDR băng rộng + BPF 1.6 GHz + LNA 1.6 GHz | ⭐⭐⭐ |
| FRB | SDR ≥ 40 MHz + trigger + may mắn | ⭐⭐⭐⭐ |
| Jupiter DAM (15–30 MHz) | **không dùng chảo** — cần dipole + RTL-SDR (dự án Radio JOVE) | ⭐ |

---

## 5. Những thứ **không** nên thử (và lý do)

| Ý tưởng | Vì sao không |
|---|---|
| Bản đồ bầu trời vô tuyến "đẹp" | beam 4°, độ nhạy thấp → chỉ ra ảnh nhoè, không có giá trị mới |
| Phát hiện FRB | fluence điển hình ~1 Jy·ms; với SEFD 70 kJy cần `B·t` khổng lồ + thời gian thực |
| Đo CMB / bức xạ nền | cần hiệu chuẩn tuyệt đối 10⁻⁵, ngoài khả năng |
| 21 cm power spectrum (EoR) | cần interferometer + hiệu chuẩn cực khó |
| Radar thiên thạch / vệ tinh | cần máy phát (không được phép) |
| VLBI | cần đồng hồ nguyên tử + ghi băng rộng |
| Jupiter DAM bằng chảo 1.4 GHz | sai tần số (DAM ở 15–30 MHz); chảo không thu được |
| Đo từ trường sao neutron | cần 2 phân cực |

---

## 6. An toàn: Mặt Trời

Với beam 4°, Mặt Trời bị pha loãng 1/64 → `T_A ≈ 13 K` (yên tĩnh). Nhưng:

- Bão mặt trời có thể làm thông lượng tăng **10–100 lần** → `T_A` tới ~1 000 K, và
  trong **búp sóng hẹp** của feed, mật độ công suất có thể đủ để **bão hoà/hỏng LNA**.
- Quy tắc: **không trỏ Mặt Trời quá 60 s**; luôn bật LNA sau khi đã trỏ đi chỗ khác;
  theo dõi `max_sigma` của ADC (GUI đã có) để phát hiện bão hoà.
- Mặt Trời chỉ dùng cho **drift scan** (để Mặt Trời đi qua beam) — đây là cách đo beam
  an toàn nhất.

---

## 7. Bản đồ khả năng theo tần số

```
  15 MHz      30        100      408      1420    1665   5000   6668
    |----------|----------|--------|--------|-------|------|------|
 Jupiter DAM   ?      HI 21cm (không dùng chảo)  |      |      |
 (dipole)      |          |        |     HI/H166α  OH    ...   CH3OH
               |          |        |        ↑
               |          |        |     dải của RTP-3.7 hiện tại
               |          |        |
               |          |      dải mở rộng nếu thay feed + LNA (300–1700 MHz)
```

Chảo 3.7 m về nguyên tắc dùng được 300 MHz – 5 GHz nếu thay feed/LNA; nhưng **cùng
một chảo không làm tốt cả hai đầu** — chọn 1.4 GHz (HI, pulsar, H166α) hoặc 408 MHz
(pulsar sáng hơn, tàn dư SNR) làm trục chính.
