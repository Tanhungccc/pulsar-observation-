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

### 4.1 SNR dự đoán — 5 cấu hình × 10 pulsar

`A` = hiện có (RTL-SDR + SAWbird, 2.4 MHz); `B` = SDR 10 MHz; `C` = SDR 40 MHz;
`D` = 408 MHz + RTL-SDR; `E` = 408 MHz + SDR 8 MHz.

**SNR trong 1 giờ / 6 giờ:**

| Pulsar | P (ms) | DM | A | B | C | D | E |
|---|---|---|---|---|---|---|---|
| **B0950+08** | 253 | 3.0 | 0.9 / 2.3 | 2.2 / 5.4 | **4.8 / 11.7** | 1.4 / 3.4 | 3.1 / 7.5 |
| B1929+10 | 227 | 3.2 | 0.4 / 0.9 | 0.9 / 2.1 | 1.9 / 4.5 | 0.6 / 1.5 | 1.3 / 3.2 |
| B1133+16 | 1188 | 4.8 | 0.5 / 1.2 | 1.2 / 2.9 | 2.6 / 6.3 | 0.9 / 2.2 | 2.0 / 4.8 |
| B0329+54 | 715 | 26.8 | 0.3 / 0.6 | 0.6 / 1.5 | 1.3 / 3.2 | 0.5 / 1.3 | 1.2 / 2.9 |
| B0833−45 (Vela) | 89 | 67.9 | 0.8 / 1.9 | 1.8 / 4.5 | **4.0 / 9.8** | 0.9 / 2.1 | 1.9 / 4.6 |
| B0531+21 (Cua) | 33 | 56.8 | 0.06 / 0.14 | 0.14 / 0.34 | 0.30 / 0.74 | 0.66 / 1.6 | 1.5 / 3.5 |
| J0437−4715 | 5.8 | 2.6 | 0.6 / 1.4 | 1.4 / 3.4 | 3.0 / 7.3 | 0.2 / 0.4 | 0.4 / 0.9 |
| B1641−45 | 455 | 475 | 0.4 / 0.9 | 0.9 / 2.1 | 1.9 / 4.6 | 0.6 / 1.5 | 1.3 / 3.2 |
| B1706−44 | 102 | 75.7 | 0.3 / 0.7 | 0.7 / 1.7 | 1.5 / 3.7 | 0.4 / 1.0 | 0.9 / 2.2 |
| B1937+21 | 1.6 | 71.0 | 0.03 / 0.08 | 0.08 / 0.20 | 0.18 / 0.43 | 0.01 / 0.03 | 0.02 / 0.05 |

**Thời gian cần để đạt SNR = 12** (giờ quan sát liên tục, lý tưởng):

| Pulsar | A | B | C | D | E |
|---|---|---|---|---|---|
| **B0950+08** | 164 h | 30 h | **6.3 h** | 73 h | **15 h** |
| B1929+10 | 1 100 h | 198 h | 42 h | 408 h | 85 h |
| B1133+16 | 567 h | 102 h | 22 h | 182 h | 38 h |
| B0329+54 | 2 230 h | 403 h | 86 h | 485 h | 101 h |
| B0833−45 | 235 h | 42 h | **9.0 h** | 193 h | 40 h |
| B0531+21 | — | 7 400 h | 1 580 h | 331 h | 69 h |
| J0437−4715 | 423 h | 76 h | 16 h | 4 650 h | 970 h |
| B1641−45 | 1 040 h | 188 h | 40 h | 406 h | 85 h |
| B1706−44 | 1 640 h | 296 h | 63 h | 881 h | 184 h |
| B1937+21 | — | — | 4 620 h | — | — |

*(“—” = trên 10 000 giờ, coi như không khả thi. Với Cua, con số fold là vô nghĩa —
đường duy nhất là giant pulse, xem §4.2.)*

*(Thực tế nhân thêm **1.5–2×** cho hiệu chuẩn, trỏ, mất mẫu, thời tiết, RFI và nhấp
nháy scintillation. Nếu `T_sys` thực là 200 K thay vì 150 K, nhân thêm 1.75×.)*

### 4.2 Cổng quyết định rút ra từ bảng

| Câu hỏi | Trả lời định lượng |
|---|---|
| Có thể phát hiện pulsar bằng thiết bị **hiện có** không? | **Không** ở L-band (164 h). **Nhưng ở 423 MHz thì được 3.8 trong 2.5 h** — xem §4.3. |
| Bước **rẻ nhất** trước tiên? | **Đổi ban nhạc sang 423 MHz** (feed + LNA + BPF, không cần SDR mới): ×4 ngay lập tức. |
| Bước **quyết định**? | SDR **10–20 MHz** ở 423 MHz → **một đêm** đạt SNR 7.7–10.9 cho B0950+08. |
| Mục tiêu số 1 là gì? | **B0950+08** (dec +7.9°, `alt_max = 87°`, DM 3.0, S ∼ 0.7 Jy @423 MHz, tháng tốt nhất: **2**). **Không** phải B0329+54 (chỉ 0.2 Jy — bài học từ TNU). |
| Mục tiêu số 2? | **Vela** (`alt_max 34°`, DM 67.9) — mạnh nhưng thấp, `T_sys` xấu. |
| Có nên làm L-band 40 MHz? | Chỉ khi muốn **một chuỗi duy nhất** cho cả HI và pulsar; đắt hơn và vẫn 6.3 h. |
| Cua (Crab) thì sao? | Fold vô vọng (duty cycle 30 %). Chỉ giant pulse, giai đoạn 4. |

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

**(1) Mục tiêu: B0329+54 không phải lựa chọn tốt nhất.** Nó chỉ 0.20 Jy @400 MHz.
Trong tầm nhìn từ TP.HCM, **B0950+08 sáng gấp 3.5 lần (0.70 Jy)** và đi qua **thiên
đỉnh (alt 87°)** → `T_sys` thấp nhất, DM 3.0 nên **không cần khử tán sắc, không tán xạ**.

**(2) Diện tích: 3.7 m so với 2.4 m = ×2.4 diện tích**, lại là mặt parabol thật
(η 0.55 so với ~0.45 của giấy thiếc) → **gain ×2.8**.

**(3) Băng thông: 6 MHz quá hẹp** khi đã có gain — đây là chỗ đáng đầu tư.

**SNR dự đoán cho kính TA ở 423 MHz, mục tiêu B0950+08** (S = 0.70 Jy, `W50` = 20 ms):

| `T_sys` | B (MHz) | 1 h | 1.5 h | 2 h | **2.5 h** | 3 h |
|---|---|---|---|---|---|---|
| 200 K | 2.4 (RTL-SDR hiện có) | 2.4 | 2.9 | 3.4 | **3.8** | 4.1 |
| 200 K | 6 | 3.8 | 4.6 | 5.3 | **5.9** | 6.5 |
| 200 K | **10** | 4.9 | 5.9 | 6.9 | **7.7** | 8.4 |
| 200 K | **20** | 6.9 | 8.4 | 9.7 | **10.9** | 11.9 |
| 300 K | 10 | 3.2 | 4.0 | 4.6 | **5.1** | 5.6 |
| 300 K | 20 | 4.6 | 5.6 | 6.5 | **7.2** | 7.9 |

**Đọc bảng này**:

- **Với RTL-SDR hiện có, chỉ cần đổi sang 423 MHz**: 2.5 h cho SNR 3.8 — tức là **×4
  so với L-band cùng thiết bị** (0.9). Đổi ban nhạc là đòn bẩy **rẻ nhất**.
- **Thêm SDR 10–20 MHz**: một đêm 2.5 h cho **SNR 7.7–10.9** → **phát hiện trong MỘT
  ĐÊM**, đúng như trực giác của bạn và của TNU.
- So với đường L-band 40 MHz (6.3 h cho SNR 12): 423 MHz + 20 MHz đạt SNR 11.9 trong
  **3 h**, với SDR **rẻ hơn** và **giữ nguyên chuỗi L-band cho HI**.

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
Thiết bị hiện có @L-band: 164 h  → KHÔNG ĐỦ
Cùng thiết bị, đổi sang 423 MHz: 2.5 h → SNR 3.8  (×4, chi phí chỉ là feed+LNA+BPF)
423 MHz + SDR 20 MHz, Tsys 200 K: 2.5 h → SNR 10.9 → PHÁT HIỆN TRONG MỘT ĐÊM
Mục tiêu #1: B0950+08 (alt 87°, DM 3.0, 0.70 Jy @423 MHz, tháng 2)
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
