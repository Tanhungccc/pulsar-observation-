# 02 — Chuỗi thu, độ nhạy và ngân sách S/N của RTP-3.7

*Mọi số trong tài liệu này sinh ra từ `code/psr_sensitivity.py` và
`code/psr_targets.py` — chạy lại được, không phải số chép tay.*

---

## 1. Chuỗi tín hiệu hiện có và yêu cầu từng khối

```
[Feed 1.4 GHz] → [LNA/SAWbird+HI] → [BPF] → [cáp] → [bias-tee] → [RTL-SDR v5] → PC
     ↑               ↑ 30 dB, NF 0.5 dB       ↑ suy hao 1–3 dB
  tiêu điểm       đặt NGAY feed
```

| Khối | Yêu cầu cho pulsar | Hiện có | Đánh giá |
|---|---|---|---|
| Feed | 50 Ω, 1 phân cực, khẩu độ khớp `f/D` | horn/dipole tại tiêu điểm | ✅ đủ cho fold |
| LNA | `NF ≤ 0.6 dB`, gain 25–35 dB, đặt sát feed | SAWbird+HI (NF ~0.5 dB, +30 dB, SAW 1420 MHz) | ⚠ SAW giới hạn băng thông ~25 MHz — **chặn đường nâng cấp** |
| BPF | 1300–1500 MHz (nếu bỏ SAW) | trong SAWbird | ⚠ cần BPF rời khi thay LNA |
| Cáp | suy hao < 2 dB (LMR-240/LMR-400) | có | ✅ |
| ADC/SDR | **băng thông ≥ 10 MHz, mẫu ≥ 20 MS/s, không mất mẫu** | RTL-SDR v5: 2.4 MS/s | ❌ **nút thắt chính** |
| Đồng hồ | ±0.5 ppm đủ cho ≤ 2 h; GPSDO cho timing dài | TCXO ±0.5 ppm | ⚠ đủ cho bước đầu |
| Ghi dữ liệu | **phổ động (kênh × thời gian) + timestamp + đếm mẫu** | `record_data.py` chỉ ghi phổ **trung bình**, không có trục thời gian | ❌ phải viết mới |

> **Phát hiện quan trọng về code hiện có**: `skTRT/skao_trt/record_data.py` đọc
> `2^21` mẫu mỗi lần rồi **cộng dồn phổ**, không lưu mốc thời gian, không kiểm tra
> mất mẫu giữa các lần đọc. Với HI thì ổn; với pulsar thì **không dùng được** vì fold
> cần trục thời gian tuyệt đối. Phải có chế độ ghi mới (§10).

---

## 2. Nhiệt độ hệ thống `T_sys` — thành phần và cách giảm

| Thành phần | 1.4 GHz | 408 MHz | Cách giảm |
|---|---|---|---|
| Receiver (LNA + sau đó) | 25–40 K | 25–40 K | LNA NF thấp, đặt sát feed |
| Spillover / mặt đất | 20–40 K | 25–50 K | chắn ground, feed đúng tiêu điểm, tránh alt < 20° |
| Khí quyển | 3–5 K | 5–8 K | không giảm được |
| CMB | 2.7 K | 2.7 K | — |
| Nền thiên hà | 2–5 K (|b| cao) | 30–80 K | chọn hướng |b| lớn |
| **Tổng thực tế** | **70–150 K** | **150–400 K** | |
| Dùng để lập kế hoạch | **150 K** | **250–300 K** | |

Toàn bộ tài liệu dùng `T_sys = 150 K` (L-band) và `250–300 K` (408 MHz) — **lạc quan
vừa phải**. Việc đầu tiên của giai đoạn 0 là **đo `T_sys` thật** bằng phương pháp
Y-factor (§9) để thay số vào bảng.

---

## 3. Gain, SEFD — và một **đính chính** cho `PROJECT_PLAN.md`

```
A_eff  = η · π D²/4                = 0.55 × 10.75 = 5.91 m²
G      = A_eff·1e-26/(2k)          = 2.14 mK/Jy
SEFD   = 2 k T_sys / A_eff         = 46.7 kJy (100 K) | 70.0 kJy (150 K) | 116.7 kJy (250 K)
HPBW   = 1.22 λ/D                  = 3.99° @1420 MHz | 13.9° @408 MHz
```

Kiểm tra chéo bằng hai đường độc lập (cả hai đều cho cùng kết quả):

- `G = A_eff/(2k) = 5.91/(2·1.38e-23) = 2.14e23 K m²/W` → 1 Jy (= 1e-26 W m⁻² Hz⁻¹)
  cho `2.14e23 × 1e-26 = 2.14 mK` ✔
- Đối chiếu thiên văn: Arecibo (305 m) có `G ≈ 10 K/Jy` → suy ra chảo 3.7 m phải
  `≈ 10 × (3.7/305)² ≈ 1.5–2 mK/Jy` (cùng bậc) ✔

### Đính chính

`PROJECT_PLAN.md` §1 ghi **SEFD ≈ 250 Jy** (T_sys 150 K) và **410 Jy** (250 K) cho
cùng chảo 3.7 m. Con số đúng là **70 040 Jy** và **116 734 Jy** — **nhỏ hơn thực tế
~280 lần**.

Kiểm tra bằng chính định nghĩa: để `SEFD = 250 Jy` với `T_sys = 150 K` cần
`A_eff = 2kT/S = 2·1.38e-23·150/250/1e-26 ≈ 1 657 m²`, tức **154 lần diện tích hình
học** của chảo 3.7 m (10.75 m²) — bất khả thi. Đây là lỗi đơn vị/số học, không phải
khác giả thiết.

**Hệ quả (đã kiểm tra bằng code)**: mọi SNR pulsar trong `PROJECT_PLAN.md` §1 và §3
bị **ước lượng cao ~170–280 lần**. Cụ thể câu "B0329+54 với RTL-SDR 2 MHz, tích luỹ
30 phút: SNR_fold ≈ 30" — giá trị đúng là **≈ 0.18**. Điều này **không** làm hỏng
chương trình HI (dòng HI 21 cm mạnh gấp ~10⁴ lần pulsar, SNR vẫn 50–200), nhưng nó
làm hỏng toàn bộ phần lập kế hoạch pulsar. Vì vậy tài liệu này thay thế phần đó.

*(Cùng loại lỗi ở bảng §3.1: "Cua ~0.5 Jy @1.4 GHz" — thực tế pulsar Cua chỉ
~10–20 mJy; 0.5 Jy là bậc của **tinh vân** Cua, không phải pulsar. "Vela ~0.4 Jy"
cũng cao hơn thực tế ~3–4 lần. Bảng S dùng trong tài liệu này là xấp xỉ **có ghi
chú**, và phải tra ATNF trước khi công bố.)*

---

## 4. Ngân sách S/N

Công thức dùng (Lorimer & Kramer 2005, ch.7), đã kiểm chứng với mô phỏng
(`selftest.py`: công thức 11.9 vs mô phỏng 11.2):

```
SNR_fold = (S_mean / SEFD) · √(n_pol · B · t) · √(P/W)
```

Cách đọc nhanh (L-band, T_sys 150 K):

| Điều kiện | Độ nhạy 1σ (thông lượng) |
|---|---|
| `B = 2.4 MHz`, `t = 1 h` (RTL-SDR hiện có) | **0.75 Jy** |
| `B = 10 MHz`, `t = 1 h` | 0.37 Jy |
| `B = 40 MHz`, `t = 1 h` | 0.18 Jy |
| `B = 40 MHz`, `t = 6 h` | 0.075 Jy |
| Fold thêm hệ số `√(W/P) = 6` (pulsar 25 mJy, duty 2.4 %) | ngưỡng hiệu dụng **12 mJy** |

Nói cách khác: **băng thông là đòn bẩy số một** (`SNR ∝ √B`), tích luỹ là đòn bẩy
số hai (`∝ √t`), `T_sys` là số ba (`∝ 1/T_sys`).

### 4.0 ⚠ ĐÍNH CHÍNH DANH MỤC (2026-11) — đọc trước khi dùng mọi bảng SNR

Bảng §4.1 dưới đây được lập bằng **thông lượng gần đúng**, và đã đối chiếu lại với
**ATNF psrcat v2.9.0** (tải `psrcat.db`, 4.503 pulsar): nhiều giá trị **sai tới ×7**.
Nguyên nhân: (a) `S400`/`S1400` bị chép tay; (b) `W50` của ATNF **đo ở 1.4 GHz**
nhưng bị dùng như W50 ở 400 MHz.

| Pulsar | S400 cũ → **ATNF** | S1400 cũ → **ATNF** | W50 cũ → **ATNF @1.4 GHz** |
|---|---|---|---|
| B0950+08 | 700 → **400** | 110 → **100** | 25 → **8,6 ms** |
| B1929+10 | 350 → **303** | 45 → **29** | 30 → **6,0 ms** |
| B1133+16 | 250 → **257** | 35 → **20** | 40 → **5,8 ms** |
| **B0329+54** | 200 → **1500** | 25 → **203** | 40 → **6,6 ms** |
| **B0833-45 (Vela)** | 700 → **5000** | 110 → **1050** | 20 → **1,7 ms** |
| B0531+21 (Cua) | 650 → 646 | 14 → 14 | 10 → **3,0 ms** |
| B1641-45 | 350 → **375** | 60 → **300** | 60 → **8,0 ms** |

Hệ quả: **Vela và B0329+54 sáng hơn B0950+08 nhiều lần**, không phải ngược lại.

`psr_targets.py` đã sửa: lấy `S400/S1400/W50(1.4 GHz)` từ ATNF, và **W50 tại tần số
quan sát được tính** bằng mô hình (không chép tay):

```
W_int(ν) = W50(1.4 GHz) · (1400/ν)^0.3
τ_sc(ν)  = 1.3e-4 · (DM/100)^2.2 · (ν/1000)^-4.4   [s]     (Bhat+2004)
W(ν)     = sqrt(W_int² + τ_sc²)
```

Kiểm tra mô hình: B1641-45 (DM 479) có **τ_sc(423 MHz) ≈ 180 ms** → bị xóa sạch ở
423 MHz, trong khi ở 1.4 GHz chỉ 4 ms → **quan sát tốt ở L-band**. Đây là lý do
phải có số hạng tán xạ, không chỉ giãn nội tại.

### 4.1 SNR dự đoán — 5 cấu hình × 10 pulsar

`A` = hiện có (RTL-SDR + SAWbird, 2.4 MHz); `B` = SDR 10 MHz; `C` = SDR 40 MHz;
`D` = 408 MHz + RTL-SDR; `E` = 408 MHz + SDR 8 MHz.

**SNR trong 1 giờ / 6 giờ:**

**Bảng TÁI SINH 2026-11 từ ATNF + mô hình W(ν) — thay toàn bộ số cũ:**

| Pulsar | P (ms) | DM | A (L 2.4) | B (L 10) | C (L 40) | D (423 2.4) | E (423 8) |
|---|---|---|---|---|---|---|---|
| B0950+08 | 253 | 3.0 | 0.7 / 1.7 | 1.2 / 2.9 | 3.6 / 8.8 | 1.2 / 2.9 | 2.6 / 6.3 |
| B1929+10 | 227 | 3.2 | 0.2 / 0.6 | 0.6 / 1.4 | 1.2 / 2.9 | 1.0 / 2.5 | 2.2 / 5.4 |
| B1133+16 | 1188 | 4.8 | 0.4 / 0.9 | 0.9 / 2.2 | 1.9 / 4.7 | 2.0 / 5.0 | 4.5 / 10.9 |
| B0329+54 | 715 | 26.8 | 2.8 / 6.8 | 6.6 / 16.1 | 14.2 / 34.9 | 8.6 / 21.1 | 18.8 / 46.1 |
| B0833-45 | 89 | 67.9 | 10.0 / 24.5 | 23.6 / 57.7 | 51.0 / 125.1 | 16.6 / 40.5 | 36.3 / 88.8 |
| B0531+21 | 33 | 56.8 | 0.1 / 0.1 | 0.1 / 0.3 | 0.3 / 0.7 | 1.1 / 2.6 | 2.4 / 5.8 |
| J0437-4715 | 6 | 2.6 | 1.3 / 3.1 | 3.0 / 7.3 | 6.4 / 15.7 | 1.9 / 4.7 | 4.2 / 10.3 |
| B1641-45 | 455 | 478.7 | 3.0 / 7.3 | 7.0 / 17.2 | 15.2 / 37.2 | 0.3 / 0.8 | 0.7 / 1.6 |
| B1706-44 | 102 | 75.6 | 0.1 / 0.2 | 0.1 / 0.4 | 0.3 / 0.8 | 0.1 / 0.1 | 0.1 / 0.3 |
| B1937+21 | 2 | 71.0 | 0.1 / 0.3 | 0.3 / 0.7 | 0.6 / 1.4 | 0.0 / 0.1 | 0.1 / 0.2 |

A/B/C = L-band (1420/1400 MHz, 2.4/10/40 MHz); D/E = 423/408 MHz (2.4/8 MHz).
Đơn vị: SNR **1 h / 6 h**. Số sinh bằng `python psr_targets.py` — không chép tay.

### 4.2 Cổng quyết định — SỬA LẠI theo số ATNF (2026-11)

| Câu hỏi | Trả lời định lượng (sau đính chính) |
|---|---|
| Phát hiện được bằng thiết bị **hiện có** (L-band 2,4 MHz)? | **Được**: Vela **10,0/h** → SNR 8 trong ~40 phút; B0329+54 2,8/h (~8 h). Các mục tiêu khác < 1,5/h. |
| Bước rẻ nhất? | **Dùng back-end 50 MHz có sẵn của kính** (không mua gì): Vela 51/h, B0329+54 14/h, B1641-45 15/h ở 40 MHz. |
| Có cần đổi sang 423 MHz? | **Không bắt buộc.** 423 MHz vẫn tốt hơn cho mục tiêu yếu (B1133+16 ×8, B1929+10 ×8 so với L-band) và beam 13° dễ trỏ — nhưng là **tuỳ chọn mở rộng**. |
| Mục tiêu số 1? | **Vela (B0833-45)** — S1400 = 1,05 Jy, W50 = 1,7 ms → SNR 8 trong vài phút. Hạn chế: altmax 34°. |
| Mục tiêu số 2–3? | **B0329+54** (1,5 Jy @400, altmax 46°) và **B1641-45** (300 mJy @1400, DM 479 — chỉ tốt ở L-band). |
| B0950+08? | Vẫn tốt (SNR 9,8/h @423; 3,1/h @L-band) nhưng **không còn là #1**. |
| Cua? | Fold ở L-band vô vọng (14 mJy); ở 423 MHz 8,8/h — dùng cho giant pulse là chính. |

---

## 4.3 Đối chiếu thực nghiệm: TNU Summer School 2026 (file PDF trong thư mục này)

Nhóm TNU đã làm **đúng hướng** và **đúng 1 đêm** — rất đáng học. Nhưng cần đọc kết quả
cho chính xác, vì nó thay đổi kế hoạch của ta theo hướng **tốt hơn**.

**Hệ của họ** (`TNU SUMMER SCHOOL 2026GROUP 1_PULSAR & HI DETECTION.pdf`):

| Thành phần | Giá trị |
|---|---|
| Chảo | **2.4 m** (nới 1.8 m bằng xốp + giấy thiếc, 12 mảnh) |
| Tần số | **423 MHz**, LNA Mini-Circuits ZKL-33ULN-S+, **LPF** SLP-450+ |
| Băng thông | 6 MS/s ≈ **6 MHz** |
| Thời gian | **2.5 giờ** |
| Mục tiêu | **B0329+54** (P 714.5 ms, DM 26.76) |
| Xử lý | PRESTO: MAD clipping, bandpass/birdie/FFT RFI masking, dedisperse, fold |
| Kết quả | P = 714.48 ms (khớp), DM = 26.76 (khớp), nhưng **"broader, weaker peak, low S/N… hard to confirm completely"** |

**Mô hình của ta dự đoán hệ đó được bao nhiêu?**

| `T_sys` giả định | SEFD | SNR dự đoán (B0329+54, 2.5 h, B = 6 MHz) |
|---|---|---|
| 150 K | 204 kJy | 1.3 |
| 200 K | 271 kJy | **1.0** |
| 300 K | 407 kJy | 0.7 |

⇒ Với chảo 2.4 m, **B0329+54 nằm dưới mức nhiễu** trong 2.5 h. Ứng viên họ báo cáo
(đúng P, đúng DM — vì đã **dùng** giá trị catalogue để fold, không phải tìm mù) có
biên độ **phù hợp với một dao động nhiễu**. Kết luận "hard to confirm completely" của
chính họ là **chính xác về mặt vật lý** — không phải họ làm sai, mà chảo 2.4 m + 6 MHz
chưa đủ.

### Nhưng có ba điều ta làm khác được — và đây là chỗ "1 đêm" trở thành thật

**(1) Mục tiêu: chọn theo số ATNF, không theo cảm tính.** (Đã đính chính — §4.0.)
B0329+54 thật ra **rất sáng** (1,5 Jy @400 MHz), còn B0950+08 chỉ **0,40 Jy**. So sánh
đúng: Vela 5,0 Jy, B0329+54 1,5 Jy, B0950+08 0,40 Jy, B1133+16 0,26 Jy.

**(2) Diện tích: 3.7 m so với 2.4 m = ×2.4 diện tích**, lại là mặt parabol thật
(η 0.55 so với ~0.45 của giấy thiết) → **gain ×2.8**.

**(3) Băng thông: 6 MHz quá hẹp** khi đã có gain — đây là chỗ đáng đầu tư.

**SNR dự đoán cho kính TA ở 423 MHz, mục tiêu B0950+08** (ATNF: S = 0,40 Jy, `W50`@423
= 12,3 ms — **bảng tái sinh 2026-11**, thay bảng cũ dùng 0,70 Jy / 20 ms):

| `T_sys` | B (MHz) | 1 h | 1.5 h | 2 h | **2.5 h** | 3 h |
|---|---|---|---|---|---|---|
| 200 K | 2.4 (RTL-SDR hiện có) | 1.8 | 2.2 | 2.5 | **2.8** | 3.0 |
| 200 K | 6 | 2.8 | 3.4 | 3.9 | **4.4** | 4.8 |
| 200 K | **10** | 3.6 | 4.4 | 5.1 | **5.7** | 6.2 |
| 200 K | **20** | 5.1 | 6.2 | 7.2 | **8.0** | 8.8 |
| 300 K | 10 | 2.4 | 2.9 | 3.4 | **3.8** | 4.1 |
| 300 K | 20 | 3.4 | 4.1 | 4.8 | **5.4** | 5.9 |

**Đọc bảng này**:

- **20 MHz + 2,5 h → SNR 8,0** (không phải 10,9 như bảng cũ): vẫn **phát hiện trong một
  đêm**, nhưng sát ngưỡng → **nên làm 2 đêm** theo quy tắc xác nhận.
- Nếu dùng **hệ RTP37 có sẵn (L-band, 50 MHz, tracking)**: Vela đạt SNR 8 trong
  **~3 phút**, B0329+54 ~25 phút, B1641-45 ~22 phút; B0950+08 cần ~6,5 h
  (xem §4.4). Đây mới là đường **rẻ nhất** — không mua gì.

### Bốn điều bắt buộc phải sửa so với hệ TNU

| Vấn đề của hệ TNU | Hậu quả | Cách làm của ta |
|---|---|---|
| Dùng **LPF 450 MHz** (không phải BPF) | Ở TP.HCM, FM 88–108 MHz và sóng hàng không lọt vào → bão hoà ADC, RFI nặng | **BPF 380–450 MHz** đặt sau LNA |
| 6 MS/s | RTL-SDR v5 chỉ tin cậy tới ~2.4–3.2 MS/s (mất mẫu ở 6 MS/s) | SDR 10–20 MHz thật (RSPdx/Pluto+) **hoặc** chấp nhận 2.4 MHz và cộng dồn đêm |
| `T_sys` chưa đo | Không biết mình đang ở đâu | Đo Y-factor trên Cas A **trước** chiến dịch |
| Chưa tách tín hiệu khỏi nhiễu bằng **đêm thứ hai** | Không thể phân biệt candidate với may mắn | **Quy tắc 2 đêm** (xem `05` §5) |

> **Kết luận cập nhật cho kế hoạch**: ưu tiên **423 MHz** thay vì L-band cho pulsar.
> Đây là thay đổi lớn nhất so với bản kế hoạch đầu tiên, và nó dựa trên **thực nghiệm
> của TNU** cộng với việc tính lại ngân sách S/N cho chảo 3.7 m.

---

### 4.4 Phương án dùng ĐÚNG hệ POAM RTP37 (L-band, đo từ datasheet)

Datasheet RTP37 (9 trang) cho biết hệ thống **không phải** "chảo cố định + RTL-SDR":

| Hạng mục | Thông số thật | Suy ra |
|---|---|---|
| Back-end **N6002** | 100 MHz–6 GHz, phân giải < 1 kHz, gain 70 dB, NF 4–5 dB, **băng tức thời 50 MHz**, 2 kênh, USB 3.0 | Không cần mua SDR; nhưng **chưa biết thời gian tích phân nhỏ nhất** |
| Front-end L-band | 1350–1450 MHz, **G/T = 13,55 dB/K** @1450, gain 33,44 dBi, HPBW **3,83°** | T_sys = G/(G/T) ≈ **97,5 K** → **SEFD ≈ 35,8 kJy** |
| Mount | Az-over-El, **tracking < 0,01°**, encoder 0,01° | **Track được 4–5 h**, không còn giới hạn T_eff ~1 h của chế độ transit |
| Phần mềm RTCS v2 | điều khiển + thu, 80 nguồn (có pulsar), hiển thị phổ, hiệu chuẩn, xuất SFU | Tối ưu cho **Mặt Trời/HI**, chưa rõ chế độ pulsar |

**SNR với số ATNF đã đính chính** (track 4 h, n_pol = 1, L-band: 50 MHz, SEFD 35,8 kJy;
423 MHz: 40 MHz, SEFD 70 kJy, W tính theo mô hình §4.0):

| Pulsar | S1400 | SNR 4 h @L-band | → thời gian đạt SNR 8 | S400 | SNR 4 h @423 | → thời gian SNR 8 |
|---|---|---|---|---|---|---|
| **B0833-45 (Vela)** | 1050 mJy | **178** | **~3 phút** | 5,0 Jy | **271** | ~2 phút |
| **B0329+54** | 203 | **50** | **~25 phút** | 1,5 Jy | **140** | ~3 phút |
| **B1641-45** | 300 | **53** | **~22 phút** | 0,38 Jy | 5 ⚠ | (bị tán xạ 180 ms) |
| B0950+08 | 100 | 12,6 | ~6,5 h | 0,4 Jy | 19 | ~40 phút |
| B1133+16 | 20 | 6,7 | ~23 h | 0,26 Jy | 33 | ~15 phút |
| B1929+10 | 29 | 4,1 | >1 đêm | 0,30 Jy | 17 | ~30 phút |
| B0531+21 (Cua) | 14 | 1,1 | không | 0,65 Jy | 18 | ~35 phút |

**Kết luận thực dụng:** với hệ có sẵn, **Vela / B0329+54 / B1641-45 là 3 mục tiêu demo
trong 30 phút**; B0950+08 không còn là "#1". Ở 423 MHz (nếu mua thêm front-end
400–450), gần như mọi mục tiêu đạt SNR 8 trong dưới 1 giờ.

### 4.5 Ma trận DỰ PHÒNG THIẾT BỊ (để không bị chặn khi hàng không đúng kỳ vọng)

| # | Tình huống | Ảnh hưởng | Phương án dự phòng | Chi phí |
|---|---|---|---|---|
| 1 | **N6002 chỉ dump phổ ≥ 0,1–1 s** (không làm được pulsar) | Chặn bài lab pulsar | Hỏi **cổng RF/IF monitor out** sau LNA → cắm SDR ngoài (Airspy Mini/USRP) chạy pipeline sẵn có | Thấp (SDR ~5–15 triệu) |
| 2 | N6002 **không có cổng IF** | Như trên, nhưng phải chế | Dùng **coupler −20 dB** ngay sau front-end; hoặc mua front-end riêng (LNA+BPF) song song | Trung bình |
| 3 | N6002 **không có timestamp** | Pha không tái lập, không cộng dồn đêm | Dùng **PPS/GPS** hoặc đánh dấu bằng xung hiệu chuẩn; ghi `t0_mjd` + NTP | Thấp |
| 4 | Không mua được **front-end 400–450 MHz** | Mất phương án 423 MHz | Dùng L-band có sẵn (Vela/B0329/B1641 vẫn đạt SNR 8 trong <30 phút) | 0 |
| 5 | **Không có calibration noise source** | Không đo được T_sys/SEFD, flux chỉ tương đối | Y-factor với **Mặt Trời/Mặt Trăng/Cas A** (kém chính xác hơn, ~20–30 %) | 0 |
| 6 | Tracking **hỏng giữa đêm** | Mất dữ liệu | Chuyển sang **transit** (T_eff 0,27 h @L-band — ngắn, nhưng vẫn dùng được cho Vela/B0329) | 0 |
| 7 | **Mưa/sét TP.HCM** | Không quan sát | Lên lịch mùa khô; surge arrester; ưu tiên mục tiêu transit ban ngày | Thấp |
| 8 | Cáp 50 m **suy hao cao** ở 1,45 GHz | T_sys tăng → SEFD tăng | Option **RF-to-fibre** | Trung bình |

**Câu hỏi bắt buộc trong RFQ** (nếu không trả lời được thì coi như rủi ro #1):
1. N6002: **thời gian tích phân nhỏ nhất**, tốc độ ra dữ liệu, có chế độ raw spectrum ≤ 1 ms?
2. Có **cổng RF/IF monitor out** (hoặc điểm tap sau LNA) để cắm SDR ngoài không?
3. **Timestamp** (PPS/GPS/NTP) và định dạng dữ liệu mở/API?

## 5. Đồng hồ, thời gian và mất mẫu

| Vấn đề | Ảnh hưởng | Cách xử lý |
|---|---|---|
| TCXO ±0.5 ppm (RTL-SDR v5) | trôi pha `0.5e-6 × t/P` chu kỳ: 1 h với P=0.09 s → 0.02 chu kỳ (ổn); 6 h → 0.12 chu kỳ (bắt đầu hại) | dò lại P mỗi 1–2 h, hoặc GPSDO |
| TCXO ±50 ppm (RTL-SDR cũ) | hỏng hoàn toàn | **kiểm tra model trước khi dùng** |
| Mất mẫu giữa các lần đọc USB | pha nhảy ngẫu nhiên → fold mất tín hiệu **mà không báo lỗi** | ghi kèm **bộ đếm mẫu**, phát hiện khoảng trống > 1 mẫu và cắt bỏ |
| Không hiệu chỉnh barycentric | trôi pha do Trái Đất quay | chấp nhận cho `t < 1 h`, `P > 0.2 s`; dùng `astropy` cho timing thật |
| `t_0` không thống nhất giữa các file | không cộng dồn nhiều đêm được | lưu UTC ở đầu mỗi block + `t_start` |

Ghi dữ liệu tối thiểu (định dạng đề xuất — "filterbank nhỏ"):

```
header: f_center, bw, nchan, tsamp, t_start_utc, sample_counter_0, n_pol, version
data  : int8 hoặc float32, shape (nchan, ntime), ghi theo block 1 s, fsync
```

`nchan = 64…512`, `tsamp = 20…100 µs` → 64 kênh × 100 µs = 640 kB/s (int8) — dễ dàng.

---

## 6. RFI ở TP.HCM — kế hoạch đối phó

| Nguồn | Tần số | Dấu hiệu | Đối phó |
|---|---|---|---|
| DVB-T2 | 470–800 MHz | nền rộng, mạnh | tránh dải; BPF chặt |
| GSM/LTE | 900/1800/2100 | vạch hẹp, mạnh | BPF 1300–1500; quan sát ban đêm ít hơn |
| TETRA/trunked | ~380–420 MHz | xung đều | rất hại cho 408 MHz → cân nhắc |
| Tia lửa điện, LED driver, sạc | băng rộng | xung đồng thời mọi kênh | **A9 zero-DM** là bắt buộc |
| Vệ tinh, máy bay | quét Doppler | vạch di chuyển | A9 + cắt thời đoạn |
| Chính máy tính/switch gần chảo | băng rộng | nền nâng khi bật/tắt | tắt nguồn xung quanh, cáp che chắn |

Quy trình: **đo phổ nền 24 h** ở 1.4 GHz (và 408 MHz nếu làm) trước khi bắt đầu
chương trình, chọn "cửa sổ" giờ + dải tần sạch. Đây là deliverable của giai đoạn 0.

---

## 7. Hiệu chuẩn (bắt buộc trước khi tin bất kỳ SNR nào)

| Bước | Cách làm | Kết quả |
|---|---|---|
| Gain/beam | drift scan **Mặt Trời** (T_A ~ 13 K sau khi tính beam dilution 1/64) hoặc **Cas A** (5.8 K) | HPBW thực, sai số trỏ |
| `T_sys` (Y-factor) | đo `P_on` trên Cas A và `P_off` cách 6°: `T_sys = T_A/(Y−1)`, `Y = P_on/P_off` | `T_sys` thật (thay 150 K) |
| Tuyến tính ADC | đo phổ với 3 mức gain; kiểm tra `P ∝ G` | phát hiện nén gain |
| Nguồn chuẩn phụ | Cyg A (3.4 K), Tau A (2.1 K), **Mặt Trăng** (3.4 K, chuyển động chậm) | thang nhiệt độ |
| Đồng hồ | so `P` đo được với ATNF sau 1 h; sai lệch = sai số đồng hồ | ppm thực tế |

`Cas A` là nguồn chuẩn tốt nhất cho chảo nhỏ: mạnh, biết chính xác, giảm 0.7 %/năm.

**Ngưỡng tự động (gatekeeper, xem `docs/07` §6c.3)** — phần mềm phải tự áp, không để
người dùng nhớ:

| Thông số | Ngưỡng | Hành động |
|---|---|---|
| Bão hoà ADC | >0,01 % mẫu chạm ngưỡng | WARN → dùng median/MAD |
| | >0,5 % | ABORT khối, tag `SATURATED`, yêu cầu giảm gain/kiểm tra BPF |
| Radiometer `σ_P/μ_P` | lệch >20 % so với `1/√(Δf·τ)` | tag `GAIN_DRIFT` (so với kênh đối chứng) |
| Spectral Kurtosis | ngoài `1 ± 3σ_SK`, `σ_SK≈√(4/M)`, M ≥ 1000 | cờ RFI, loại kênh |
| `T_sys` | >1,5 × chuẩn | kiểm tra góc Mặt Trời + elevation <15° → `DEGRADED` |
| `ΔT_LNA` | >2 °C trong phiên | rút cửa sổ bandpass 600 s → 180 s |

---

## 8. Những gì **không** làm được với thiết bị hiện tại (và lý do)

| Mong muốn | Vì sao không | Cần gì |
|---|---|---|
| Phát hiện pulsar thường | `B·t` thiếu ~10² | SDR ≥ 10–40 MHz + 6 h |
| Khử tán sắc kết hợp (microstructure) | mất mẫu giữa các lần đọc, block ngắn | stream liên tục, ghi IQ thô, GPSDO |
| Timing dài hạn (P, Ṗ) | trôi đồng hồ, không barycentric | GPSDO + PINT |
| RM / hình học từ trường | 1 phân cực | feed 2 phân cực + hiệu chuẩn |
| Giant pulse Cua (µs) | băng thông hẹp + chưa có A3 | B ≥ 10 MHz + A3 |
| Pulsar trong quần tinh / MSP | SNR quá thấp | mọi thứ ở trên + chảo lớn hơn |

---

## 9. Tóm tắt một trang (dán lên tường)

```
A_eff = 5.91 m²      G = 2.14 mK/Jy      beam = 4.0° @1.42 GHz | 13.4° @423 MHz
SEFD  = 70 kJy @Tsys 150 K (L-band)  |  93 kJy @Tsys 200 K (423 MHz)
1σ (2.4 MHz, 1 h) = 0.75 Jy @L-band   |   SNB_fold = (S/SEFD)·√(B·t)·√(P/W)
Hệ RTP37 có sẵn @L-band 50 MHz + tracking: Vela 3 phút | B0329+54 25 phút | B1641-45 22 phút  (SNR 8)
423 MHz (nếu mở rộng) 40 MHz: B0950+08 40 phút | B1133+16 15 phút | B1929+10 30 phút
Flux ATNF: Vela 5,0 Jy | B0329+54 1,5 Jy | B0950+08 0,40 Jy  (@400 MHz)
Mục tiêu #1: Vela (S1400 = 1,05 Jy) — KHÔNG còn là B0950+08
QUY TẮC: SNR ≥ 6–8 VÀ thấy lại đêm thứ hai, đúng pha
```

## 10. Việc phải sửa trong code hiện có

1. **`record_data.py`**: thêm chế độ `record_dynamic_spectrum()` — trả về
   `(nchan, ntime)` + `t_start_utc` + `sample_counter`, kiểm tra mất mẫu.
2. **`sdr_wrapper.py`**: thêm `read_samples_stream()` liên tục, và `MockRtlSdr`
   phải mô phỏng cả **mất mẫu** để test.
3. **`constants.py`**: thêm `SEFD`, `GAIN_K_JY`, `TSYS` để GUI hiển thị trục K thay
   vì "a.u.".
4. **GUI**: thêm tab "Pulsar" (chọn mục tiêu từ ATNF → tự trỏ → ghi → fold → hiện
   hồ sơ xung + SNR), dùng `code/psr_core.py` làm backend.
5. **Đính chính** `PROJECT_PLAN.md` §1 và §3 (SEFD + SNR + bảng thông lượng).
