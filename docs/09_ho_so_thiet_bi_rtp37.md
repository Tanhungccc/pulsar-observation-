# 09 — HỒ SƠ THIẾT BỊ THỰC TẾ: POAM RTP-37 (TP.HCM)

> **Tài liệu này là nguồn duy nhất** tổng hợp mọi thông tin phần cứng đã thu thập được
> đến **2026-11-23**. Mỗi mục ghi rõ **nguồn** để phân biệt:
> `[DS]` datasheet/tài liệu hãng · `[ẢNH]` đọc từ ảnh hiện trường · `[ĐO]` đo từ dữ
> liệu xuất ra · `[TÍNH]` suy ra bằng công thức trong repo · `[?]` còn chưa biết.
>
> Khi có số đo mới, **cập nhật ngay vào đây** rồi mới sửa `configs/rtp37-hcmc.json`.

---

## 1. Trạm và chảo

| Hạng mục | Giá trị | Nguồn |
|---|---|---|
| Trạm | TP.HCM · `10.7769°N, 106.7009°E` · UTC+7 | `[TÍNH]`/hồ sơ |
| **Toạ độ đang nhập trong RTCS** | **106.7900°E / 10.7600°N** (một ảnh khác ghi 106.7005/10.7600) | `[ẢNH]` |
| Sai lệch do nhập sai | ~0,09° kinh độ ⇒ lệch pointing ~0,9° ở 4 GHz, lệch transit ~0,6 s | `[TÍNH]` |
| Đường kính | 3,7 m · η ≈ 0,55 ⇒ **A_eff = 5,91 m²** | `[DS]`/hồ sơ |
| Mount | El/Az, **nâng hạ bằng jackscrew** (linear actuator), có **resolver** + **công tắc hành trình** cho cả AZ và EL | `[DS]` mục 3.6, `[ẢNH]` |
| Hành trình cơ khí | **AZ 0–360° · EL 0–90°** | `[DS]` §1.1 |
| Cột thu lôi | có, gắn cạnh chảo | `[ẢNH]` |
| Hướng dẫn lắp đặt | `RADIO DATA/3.7-m-Antenna-Assembely and Installation-v6-1.pdf` (40 trang); §6.2.2 *Setting the Elevation Limits* | `[DS]` |

### 1.1 Feed / đầu thu ngoài trời
| Hạng mục | Giá trị | Nguồn |
|---|---|---|
| Hộp tại tiêu điểm | in **“C-Band”** (LNB/block-downconverter), ngõ ra **coax N-type** | `[ẢNH]` |
| Phân cực | **2 kênh POL riêng (POL1, POL2)**, mỗi kênh 1 motor quay | `[ẢNH]` ACU |
| Vị trí POL hiện tại | **−180,00°** (cả POL1 và POL2) | `[ẢNH]` |
| LO của LNB | **[?]** chưa đọc được nhãn — cần ảnh cận (giả thuyết: 5150 hoặc 5750 MHz) | `[?]` |
| Suy ra: 1,5 GHz trên màn hình | không khớp LO C-band chuẩn ⇒ nhiều khả năng **receiver đang tune trực tiếp 1,5 GHz** từ một nhánh feed khác, **hoặc** LNB có LO đặc biệt | `[?]` |

---

## 2. Tủ rack: 3 khối POAM Electronics

### 2.1 `Radio Telescope Receiver` (khối xanh trên cùng)
| Thông số | Giá trị | Nguồn |
|---|---|---|
| Dải thu | **100 MHz – 6 GHz** | `[DS]` §4.1.1 |
| Băng thực tức thời | **50 MHz** (tối đa) | `[DS]` §4.1.1 |
| Gain | **0–70 dB**, bước 1 dB | `[DS]` |
| Số kênh | **RTRS #1…#8** (Line = 1 kênh "Focus", Continuum = cả 8) | `[DS]` §4 |
| **IQ rate** | **tối đa 15 MS/s**, mặc định **10 MS/s** ("does not affect the power measurement mode") | `[DS]` |
| Ngõ ra | **USB3 + LAN** (chưa chụp mặt sau → chưa rõ cổng IF analog) | `[ẢNH]` |
| Phổ xuất ra | **2048 điểm**, Δf **20 kHz** cho span 50 MHz | `[ĐO]` |
| Tốc độ continuum | **0,1 / 1 / 10 Hz** | `[DS]` §4.3 |

### 2.2 `Antenna Drive Unit` (khối giữa, đen)
| Hạng mục | Giá trị | Nguồn |
|---|---|---|
| Nguồn | **24 V** (LED xanh) | `[ẢNH]` |
| LED trạng thái | `AZ encoder` · `EL encoder` · `POL encoder` · `24V` | `[ẢNH]` |
| Công tắc tay | `CW/CCW (AZ)` · `UP/DOWN (EL)` · `CW/CCW (POL)` · `Power` | `[ẢNH]` |
| Khoá | **Local / Remote** | `[ẢNH]` |

### 2.3 `Antenna Control Unit` (khối dưới, có màn hình cảm ứng)
| Hạng mục | Giá trị | Nguồn |
|---|---|---|
| Hiển thị | `AZ Cur/TRGT`, `EL Cur/TRGT`, `POL Cur/TRGT`, `AGC`, `ADU T/H` (°C/%) | `[ẢNH]` |
| LED | `AZ CW/CCW` · `EL UP/DOWN` · `POL1·POL2 CW/CCW` · `AZ·EL·POL Coder` · **`Handy box`** · **`COM`** · **`GPS`** · `IO` · `ADU 24V` | `[ẢNH]` |
| Nút chức năng | AZ CW/CCW · EL UP/DOWN · Pol1 CW/CCW · Pol2 · **Stow** · Menu · Move · **Track** · **Satellite** · Setting · Log | `[ẢNH]` |
| Phiên bản | `V1.5c03` | `[ẢNH]` |
| **Sự cố đang có** | `Alarm EL DOWN LIMIT` (EL 28,905 → 29,677° mà vẫn báo) ⇒ giới hạn cứng đặt **≈29–30°** | `[ẢNH]` |
| AGC | **0.0** (chưa có tín hiệu/ chưa nối) | `[ẢNH]` |
| Nhiệt ẩm trong hộp | 42,1 °C / 37,3 % → 40,6 °C / 40,6 % | `[ẢNH]` |
| Đồng hồ | `LOCAL = GMT` (UTC+0) **≠** Time Zone 7 trong RTCS | `[ẢNH]` |
| Nhập remote | ACU `Settings` → mật khẩu **222222** → chuyển remote | `[DS]` §3 |

---

## 3. Phần mềm RTCS v2.2 (tài liệu `RTC_v2.1.0`)

| Hạng mục | Giá trị | Nguồn |
|---|---|---|
| Bám nguồn | **theo RA/Dec** (Celestial Object Tracking), nhập *Tracking time* (phút), **độ chính xác 1 / 0,5 / 0,3°** | `[DS]` §5.1 |
| Cơ sở dữ liệu | **80 nguồn mạnh, có cả pulsar** + Mặt Trời | `[DS]` §1.1 |
| Bám Mặt Trời | tự động theo lịch (sunrise→sunset) và thủ công | `[DS]` §5.2 |
| Quan sát | **Line Observation** (phổ, 1 kênh) và **Continuum** (8 kênh, total power) | `[DS]` §4.2–4.3 |
| Quét | `Scanning`: **Area 4,00 deg² · step 0,50° · int time 10 s**, chọn nguồn (Mặt Trời…), xuất tham số quét | `[DS]` §7 |
| Xuất dữ liệu | Phổ **chỉ của Focus Receiver**; công suất **mọi kênh chọn**; header tự ghi tham số receiver + thời điểm đầu/cuối | `[DS]` §4.4 |
| Điều khiển ACU | **TCP hoặc Modbus**; Modbus dùng `192.168.1.10`, không cần port | `[DS]` §3 |
| Hiệu chuẩn | **`Calibrator Unit`**: tham số **ECA** (diện tích hiệu dụng) và **ENR nhập bằng °C** | `[DS]` §9, Appendix A |
| **Công thức Appendix A** | `Tn = (Tamb − 24)·0,1 + ENR + 273,5` (K) · `SFD = (Psun−Psky)/(Pn−Pload) · (Tn−Tload) · 2k·e^τ·L /(α·A_CE)` | `[DS]` tr.49 |
| Chuyển toạ độ | Appendix B: `sin El = sinDec·sinφ + cosDec·cosφ·cosH`, `H = LST − RA` | `[DS]` tr.50 |

### 3.1 Hiện trạng phiên đang chạy `[ẢNH]`
| Trường | Giá trị |
|---|---|
| Cấu hình RTRS #1 | IQ Rate **10,000 MS/s** · Samples **2048** · Centre **1,500 GHz** · Gain **20 dB** · Bandwidth **50 MHz** |
| RTRS #2–#8 | IQ 10 MS/s · Samples 2040 · Centre 2,450 GHz · Gain 0 · BW 200 kHz |
| Đồ thị | Spectrum 1,475–1,525 GHz (−80…−140 dBm) · Intensity (waterfall) 1,495–1,505 GHz, thang −78,27…−155,7 dBm |
| Thời gian | `LT 16h32m` · `LST 20h48m58,27s` · `JD 2461367,8974` |
| Mặt Trời (Object Readout) | RA 15h55m51,9s · Dec −20°22′34″ · Az 246,712° · El 10,430° · Flux(1420 MHz) hiển thị theo mục catalogue |
| Bản đồ sao | 3C 48 · 3C 147 · 3C 161 · 3C 218 · 3C 274 (Vir A) · 3C 279 · 3C 286 · 3C 295 · 3C 433 · 3C 452 · 3C 454.3 · CYG A · CTA 39 · SUN + P1…P20 |
| Lỗi hệ thống | banner đỏ `System Issue` (23/11 16:32–16:39) |

---

## 4. Dữ liệu xuất ra đã có (`D:\Radio Telescope\RADIO DATA`)

| Tệp | Định dạng | Đo được `[ĐO]` |
|---|---|---|
| `line.csv` / `Line observation.txt` | `Frequency (Hz)` \| `Power (dBm)` | 2048 điểm · 1475–1525 MHz · Δf 20 kHz · TB **−100,1 dBm** · σ 5,58 dB · đỉnh **1499,99 MHz = −86,1 dBm (+14,0 dB)** |
| `continuum observation.txt` / `.csv` | `Time` \| `dBm` × 8 kênh | 1024 mẫu (98–1121 s) · TB −76,9 dBm · **trôi −1,90 dB/phút** · p2p 76,8 dB |
| `123.txt` | `AZ-deg` \| `EL-deg` \| `RTRS1` | 147 điểm · AZ 0,6–237,8° · EL 33,6–57,2° · 94 điểm có số · p2p 79,7 dB |
| `…v2.2.pdf`, `3.7-m-…v6-1.pdf` | tài liệu hãng | 51 + 40 trang |

**Quan trọng:** các tệp này **chỉ có phổ đã tích phân và công suất ≤10 Hz** ⇒ **không
fold được pulsar** (mất pha; P(Vela) = 89,3 ms < 100 ms của nhịp 10 Hz).

---

## 5. Hiệu năng suy ra `[TÍNH]` (A_eff = 5,91 m², công thức trong `psr_constants`, `psr_sensitivity`)

| Băng | HPBW | T_sys giả định | SEFD | Vela 2,5 h (B = 10 MHz) | B = 50 MHz |
|---|---|---|---|---|---|
| 423 MHz | **13,17°** | 150 K | 70,1 kJy | — | — |
| 1,42 GHz | 3,92° | 97,5 K | 45,6 kJy | **SNR 19,5** | SNR 43,5 |
| 1,50 GHz (đang tune) | 3,71° | 97,5 K | 45,6 kJy | **SNR 19,5** | SNR 43,5 |
| 4,0 GHz (feed C-band) | **1,39°** | 80 K | 37,4 kJy | SNR 4,5 | SNR 10,1 |

Ghi chú: **băng hữu ích = IQ rate** (10 MS/s ⇒ 10 MHz), *không phải* 50 MHz của bộ lọc
analog. Muốn 50 MHz thật phải nâng IQ lên ≥ 50 MS/s (vượt mức 15 MS/s của thiết bị) ⇒
thực tế tối đa **15 MHz**.

### 5.1 Ràng buộc hình học ở vĩ độ 10,78°N
`EL_max = 90° − |10,7769° − δ|`, và **giới hạn cứng EL ≥ ~30°**:

| Nguồn | δ | EL_max | Đánh giá |
|---|---|---|---|
| B0950+08 | +8,0° | 87,2° | tốt nhất, gần thiên đỉnh |
| B0329+54 | +54,7° | 46,1° | tốt |
| Crab (B0531+21) | +22,0° | 78,8° | tốt |
| B0833-45 (Vela) | −45,0° | **34,2°** | chỉ quanh transit |
| B1641-45 | −45,8° | **33,4°** | quanh transit, lại DM 478,7 |

---

## 6. Câu hỏi còn treo với POAM `[?]`

1. **API/giao thức xuất luồng IQ 10–15 MS/s** (mạng hoặc tệp) — nếu không có, không thể
   làm pulsar bằng chính receiver này.
2. **Ngõ ra IF analog** nằm ở cổng nào trên mặt sau receiver (để cắm SDR ghi song song).
3. **LO của LNB C-band** (5150 / 5750 MHz?) và nguồn của băng 1,5 GHz đang thu.
4. **ENR thật** của noise source trong Calibrator Unit (°C), và cách bật/tắt trong phần mềm.
5. **Bản đồ thanh ghi Modbus** (`192.168.1.10`) để app tự ra lệnh AZ/EL/TRACK và đọc lại vị trí.
6. **Giới hạn EL cứng** đặt bao nhiêu (hiện ~29–30°) và quy trình clear `EL DOWN LIMIT`.
7. **RMS bề mặt chảo** (quyết định dùng được 4 GHz hay không: cần < λ/16 ≈ 4,7 mm).

---

## 7. Checklist buổi ra đài tiếp theo (thứ tự bắt buộc)

1. **Sửa toạ độ trong RTCS** → `106.7009°E / 10.7769°N`, kiểm tra lại Time Zone = 7.
2. **Xử lý `EL DOWN LIMIT`** theo manual §6.2.2 (mật khẩu ACU `222222` nếu chỉnh phần mềm);
   xác nhận chảo hạ/bám được tới EL 33–34° cho Vela.
3. **Ba phép đo hiệu chuẩn:**
   - *Scan qua Mặt Trời* → HPBW thực tế + độ lệch tâm búp (so với 1,39° @4 GHz / 3,7° @1,5 GHz).
   - *ON–OFF 5 phút nguồn mạnh / 5 phút trời trống*, bật–tắt Calibrator Unit → T_sys, ENR,
     tốc độ trôi gain thực (đã thấy −1,9 dB/phút trong log cũ).
   - *Phổ Line tại 1420 MHz* (vạch HI hướng mặt phẳng Ngân Hà) → kiểm tra ổn định tần số.
4. **Kiểm tra AGC**: phải khác 0 khi chĩa Mặt Trời; nếu vẫn 0 → đứt coax / chưa cấp nguồn LNB.
5. **Hỏi POAM** 2 câu ở §6 mục (1) và (2) trước khi kết thúc buổi.

---

## 8. Nhật ký cập nhật

| Ngày | Nội dung |
|---|---|
| 2026-11-22 | Dựng hồ sơ ban đầu từ datasheet RTP-37 + N6002 (docs/02 §4.4) |
| 2026-11-23 | Bổ sung ảnh hiện trường: feed C-band, Drive Unit 24 V (AZ/EL/POL), ACU V1.5c03 + `EL DOWN LIMIT`, AGC 0.0, GPS tắt; đọc ảnh RTCS: RTRS ×8, IQ 10 MS/s, B 50 MHz, gain 20 dB, tune 1,5 GHz; phân tích 3 tệp xuất trong `RADIO DATA` |
