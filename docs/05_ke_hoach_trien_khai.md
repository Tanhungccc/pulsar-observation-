# 05 — Kế hoạch triển khai (có cổng quyết định, không đốt thời gian vào việc bất khả thi)

*Ràng buộc: kính POAM RTP-3.7 (3.7 m, L-band), TP.HCM (lat 10.78° N).
Mọi con số S/N lấy từ `02`; phương pháp lấy từ `01`; code ở `code/`.*

---

## 0. Ba nguyên tắc

1. **Đo được mới tin.** Không lập kế hoạch quan sát trên `T_sys` giả định. Giai đoạn 0
   là đo `T_sys`, SEFD, beam, RFI **thật**.
2. **Kiểm chứng bằng "tiêm tín hiệu" (injection).** Trước khi tin pipeline, ta **tiêm
   một pulsar tổng hợp vào dữ liệu THẬT đã ghi** và kiểm tra pipeline tìm lại đúng
   `P`, `DM`, SNR như đã tiêm. Nếu không làm bước này, mọi "phát hiện" sau đó đều
   không đáng tin.
3. **Cổng quyết định.** Mỗi giai đoạn có tiêu chí PASS/FAIL rõ ràng. FAIL thì **dừng
   và sửa**, không chuyển sang giai đoạn sau.

---

## 1. Các cổng quyết định

| Cổng | Sau giai đoạn | Tiêu chí PASS | Nếu FAIL |
|---|---|---|---|
| **G0** | 0 — hiện trạng | `T_sys ≤ 200 K` @1.4 GHz; beam ≈ 4°; RFI đã bản đồ hoá; `selftest` 16/16 | Sửa front-end (LNA/feed/chắn ground) trước khi làm gì khác |
| **G1** | 1 — ghi dữ liệu | Recorder ghi **liên tục 2 h, 0 mẫu mất**, có UTC + đếm mẫu; injection test tìm lại được tín hiệu tiêm (SNR lệch < 30 %) | Sửa recorder; không quan sát thật |
| **G2** | 2 — nâng cấp | `B ≥ 10 MHz` hoạt động ổn định, `T_sys` không xấu hơn 1.5× | Dùng phương án B (408 MHz + RTL-SDR) hoặc C (stacking nhiều đêm) |
| **G3** | 3 — chiến dịch | **B0950+08: SNR ≥ 8** ở hồ sơ fold, kiểm chứng lại ở đêm khác | Chuyển sang upper-limit + 408 MHz; xem lại `T_sys` thực |
| **G4** | 4 — khoa học | Đo được `DM` (A11b), `W50`, `α` (nếu 2 dải tần) | Giữ ở mức "phát hiện + hồ sơ xung" |

---

## 2. Giai đoạn 0 — Hiện trạng & hiệu chuẩn (tuần 1–2)

| # | Việc | Sản phẩm | Tiêu chí chấp nhận |
|---|---|---|---|
| 0.1 | Chạy `python code/selftest.py` | log 16/16 PASS | không FAIL nào |
| 0.2 | Đo `T_sys` bằng Y-factor trên **Cas A** (`T_A = 5.8 K`) | `tsys_k` + sai số | `T_sys` trong 70–250 K; nếu > 300 K phải tìm nguyên nhân |
| 0.3 | Drift scan **Mặt Trăng** → HPBW thực + pointing model | beam (độ), offset encoder | HPBW 3.5–4.5°; offset < 1° |
| 0.4 | Khảo sát RFI **24 h** @1.4 GHz (GUI hiện có) | bảng giờ/dải sạch | chọn được cửa sổ ≥ 4 h sạch |
| 0.5 | Đo tuyến tính ADC (3 mức gain) | hệ số nén gain | `P ∝ G` trong 10 % |
| 0.6 | **Đính chính** `PROJECT_PLAN.md` §1, §3.1, §3.2 (SEFD/SNR) | bản sửa | khớp `docs/02` |

> **Vì sao bước 0.2 quan trọng nhất**: `SNR ∝ 1/T_sys`. Nếu `T_sys` thực là 250 K thay
> vì 150 K, mọi thời gian quan sát phải nhân **2.8×**. Biết sớm để khỏi phí 2 tháng.

---

## 3. Giai đoạn 1 — Ghi dữ liệu & kiểm chứng pipeline (tuần 3–6)

| # | Việc | Sản phẩm | Tiêu chí |
|---|---|---|---|
| 1.1 | `record_dynamic_spectrum()`: ghi (nchan × ntime) + UTC + đếm mẫu | module mới trong `skao_trt/` | 2 h liên tục, `dropped_samples = 0` |
| 1.2 | Kiểm tra **mất mẫu**: tiêm xung test qua bộ tạo tín hiệu/đèn LED? hoặc so `sample_counter` với `Δt·fs` | báo cáo | sai lệch < 1 mẫu/2 h |
| 1.3 | Nối `code/psr_core.py` vào recorder → pipeline trên dữ liệu thật | `run_pulsar_obs.py` | chạy hết 2 h trong < 10 phút CPU |
| 1.4 | **Injection test**: tiêm pulsar tổng hợp (P, DM, S biết trước) vào dữ liệu thật | hình + bảng | tìm lại đúng P (±100 ppm), DM (±5 %), SNR lệch < 30 % |
| 1.5 | Tự động hoá: metadata YAML theo mẫu ở `docs/03` §7 | mẫu + validator | mọi file có đủ trường bắt buộc |

**Deliverable**: có thể ghi 2 h dữ liệu thật và tìm lại một pulsar **tổng hợp** trong
đó. Đây là bằng chứng pipeline đúng **trước khi** tiêu hao thời gian kính cho pulsar thật.

---

## 4. Giai đoạn 2 — Nâng cấp phần cứng (tuần 5–8, mua sắm song song GĐ1)

### Phương án A (KHUYẾN NGHỊ sau khi đối chiếu TNU): **423 MHz**

Đây là thay đổi lớn nhất so với bản kế hoạch đầu, dựa trên thực nghiệm TNU + tính lại
ngân sách S/N (`docs/02` §4.3). Lý do: pulsar sáng gấp **6–7 lần** ở 423 MHz so với
1.4 GHz, nên **không cần** băng thông 40 MHz đắt tiền.

| Hạng mục | Yêu cầu | Vì sao |
|---|---|---|
| Feed 423 MHz | dipole nửa sóng + mặt phản xạ, hoặc loop + ground plane (λ = 71 cm) | thay feed L-band |
| LNA | NF ≤ 0.6 dB, 300–500 MHz (vd. ZKL-33ULN-S+ như TNU) | `T_sys` quyết định mọi thứ |
| **BPF 380–450 MHz** | **bắt buộc** (TNU dùng LPF → sai lầm ở TP.HCM) | chặn FM 88–108, hàng không, TETRA |
| SDR | **10–20 MHz** (RSPdx / Pluto+); RTL-SDR 2.4 MHz chỉ là tạm | `SNR ∝ √B` |
| Cáp + chống sét | LMR-400, tiếp địa | như A2 |

Kết quả kỳ vọng: **B0950+08, 2.5 h, một đêm** → SNR **7.7** (10 MHz) hoặc **10.9**
(20 MHz) với `T_sys = 200 K`. Chuỗi L-band (SAWbird + HI) **giữ nguyên** cho HI.

### Phương án B: L-band băng rộng 40 MHz (nếu muốn một chuỗi duy nhất)

| Hạng mục | Yêu cầu | Vì sao |
|---|---|---|
| SDR 40–56 MHz | Pluto+ / LimeSDR Mini | `SNR ∝ √B`: 2.4→40 MHz = ×4.1 |
| Bỏ SAWbird+HI, thay LNA | NF ≤ 0.7 dB, 1.2–1.6 GHz | SAW giới hạn ~25 MHz |
| BPF 1300–1500 MHz | sau LNA | chặn GSM/DVB |

Kết quả: `T_sys ≈ 100–130 K`, `B = 40 MHz` → B0950+08 **6.3 h** cho SNR 12.
Ưu: không có RFI 400 MHz; nhược: đắt hơn, vẫn cần 6 h.

### Phương án C (không mua gì): đổi sang 423 MHz + cộng dồn nhiều đêm

Chỉ cần **feed + LNA + BPF 423 MHz** (~5–8 tr), giữ RTL-SDR 2.4 MHz:
- **1 đêm 2.5 h → SNR 3.8** (đã là ×4 so với L-band cùng thiết bị)
- 2 đêm → 5.4 · **4 đêm → 7.6** (ngưỡng phát hiện)

Đây là phương án **phù hợp nhất với thời gian ở trường**: mỗi phiên 2.5 h, tổng 4 phiên
trong 4 tuần, không cần mua SDR mới.

### Nhận xét về TNU (ghi để không lặp lại)

Hệ 2.4 m / 6 MHz / 2.5 h của TNU có SNR **lý thuyết ≈ 1** cho B0329+54 → ứng viên họ
báo cáo nằm trong mức nhiễu (chính họ kết luận "hard to confirm"). Ba điều ta làm khác:
**mục tiêu sáng hơn 3.5×** (B0950+08), **diện tích ×2.4 + hiệu suất cao hơn**,
**BPF thay LPF** và **quy tắc 2 đêm**.

---

## 5. Giai đoạn 3 — Chiến dịch quan sát (tuần 9–16)

Mục tiêu theo thứ tự **chắc chắn → tham vọng**:

| Thứ tự | Mục tiêu | `alt_max` | Tháng tốt | Thời gian | SNR kỳ vọng (B=40 MHz) |
|---|---|---|---|---|---|
| 1 | **B0950+08 @423 MHz, 20 MHz, `T_sys` 200 K** | 87.1° | 2 | **2.5 h × 1 đêm** | **10.9** |
| 1b | B0950+08, đêm thứ hai (xác nhận, đúng pha) | — | 2 | 2.5 h | 10.9 (cộng → 15.4) |
| 1c | B0950+08 với **RTL-SDR 2.4 MHz** (không mua SDR) | 87.1° | 2 | 2.5 h × **4 đêm** | 3.8 → **7.6** |
| 2 | B1929+10 @423 MHz | 89.8° | 7 | 2.5 h × 2 đêm | 3.5 → 5.0 |
| 3 | **Vela** (B0833−45) | 34.0° | 1 | 2.5 h × 3 đêm | 4.0 |
| 4 | B1133+16 | 85.0° | 3 | 2.5 h × 4 đêm | 3.7 |
| 5 | B0329+54 (**bài học TNU**: chỉ 0.2 Jy — để sau) | 46.2° | 11 | 2.5 h × 8 đêm | 1.6 → 4.5 |
| 6 | Cua (giant pulse) | 78.8° | 12 | nhiều đêm | (xác suất thấp) |

Quy trình mỗi đêm (6 h):

```
1. Trỏ Cas A 5 phút  → hiệu chuẩn gain/T_sys của đêm
2. Trỏ mục tiêu      → ghi 5.5 h (timestamp + đếm mẫu)
3. Trỏ Cas A 5 phút  → kiểm tra gain không trôi
4. Xử lý tự động: RFI → DM (A11b) → fold → SNR → lưu metadata
5. Ghi vào sổ: SNR, T_sys, thời tiết, RFI
```

**Quy tắc khoa học**: một phát hiện chỉ được công nhận khi
(a) SNR ≥ 8, (b) thấy lại ở **đêm khác**, (c) xuất hiện **đúng pha** dự đoán từ `P`
catalogue, (d) không xuất hiện khi trỏ lệch 8° (kiểm tra nền).

---

## 6. Giai đoạn 4 — Mở rộng (tháng 5–12)

| Việc | Điều kiện | Giá trị |
|---|---|---|
| `Ṗ` → `B`, tuổi | GPSDO + barycentric (PINT) + 6 tháng TOA | Cao (lần đầu đo được) |
| Chỉ số phổ `α` | thêm dải 408 MHz | Trung bình, dễ |
| Giant pulse Cua | A3 (stream liên tục) + `B ≥ 10 MHz` | Cao nhưng xác suất thấp |
| 2 phân cực → RM | feed mới + hiệu chuẩn phân cực | Cao, chi phí lớn |
| FFA / blind search | CPU + PRESTO | Huấn luyện, xác suất phát hiện mới ~0 |
| Đo `T_sys`/SEFD thành chuẩn công bố | đã có từ GĐ0 | Nền cho mọi kết quả khác |

---

## 7. Thiết bị & chi phí (giá tham khảo, **phải báo giá thực tế**)

| Hạng mục | Ưu tiên | Giá tham khảo |
|---|---|---|
| SDR 10–56 MHz (Pluto+/LimeSDR Mini/RSPdx) | **Bắt buộc** | 5–12 tr VND |
| BPF 1300–1500 MHz | **Bắt buộc** | 1–2 tr |
| LNA L-band NF ≤ 0.7 dB (ZX60-P103LN+ / PGA-103) | **Bắt buộc** | 1.5–3 tr |
| Cáp LMR-400 + đầu + chống sét + tiếp địa | **Bắt buộc** | 3–5 tr |
| GPSDO + bộ chia | Giai đoạn 4 | 4–8 tr |
| Feed + LNA + BPF 408 MHz (phương án B) | Tùy chọn | 4–7 tr |
| Feed 2 phân cực | Giai đoạn 4 | 5–15 tr |
| Ổ cứng 1–2 TB | Bắt buộc | 1–2 tr |
| **Tổng tối thiểu (phương án A)** | | **≈ 15–25 tr VND** |
| **Tổng tối thiểu (phương án B)** | | **≈ 8–14 tr VND** |

---

## 8. Lịch theo mùa (rút từ `psr_targets.py`, chu kỳ 1 năm)

| Tháng | Mục tiêu chính | Ghi chú |
|---|---|---|
| 1 | **Vela**, J0437−4715 | Vela chỉ cao 34°, cần trời trong |
| 2 | **B0950+08** ← *mục tiêu số 1* | gần thiên đỉnh, DM thấp |
| 3 | B1133+16 | |
| 6–8 | (mùa mưa) — ưu tiên **HI** + hiệu chuẩn + viết báo cáo | mưa ít ảnh hưởng 1.4 GHz nhưng ảnh hưởng thiết bị |
| 11 | B0329+54 | |
| 12 | **Cua** (giant pulse), Tau A | |

---

## 8b. Quan sát ban ngày — hoàn toàn được, khác hẳn quang học

Sóng vô tuyến **không** bị "ánh sáng ban ngày" làm phiền: bầu trời không sáng lên,
vì Mặt Trời là **một nguồn ở một hướng**, không phải nền sáng toàn bầu trời. Với
chảo 3.7 m, ban ngày `T_sys` gần như **không đổi** — miễn giữ Mặt Trời đủ xa.

**Quy tắc tách Mặt Trời** (tính từ `T_A = 2.14 mK/Jy × 4×10⁵ Jy = 857 K`):

| Tách Mặt Trời–trục chùm | Mức tăng nhiễu | Kết luận |
|---|---|---|
| < 4° (trong chùm chính) | tới **857 K** | ❌ không bao giờ trỏ |
| 4–10° | 100–430 K | ❌ |
| 10–25° | 1–30 K | ⚠ chỉ khi buộc phải |
| **> 45°** | **< 0.3 K** | ✅ an toàn, dùng quy tắc này |

Ngoài ra: **bão Mặt Trời** (burst type II/IV) có thể tăng nhiễu 10–100× trong vài
phút và làm nhiễu tầng điện ly → kiểm tra thời tiết không gian trước buổi quan sát;
nếu `T_sys` nhảy bất thường thì dừng.

**Pulsar nào quan sát ban ngày được?** Pulsar nào có `RA ≈ RA_Mặt Trời` thì đi qua
trung tuyến lúc giữa trưa → mỗi pulsar có "mùa ban ngày" ~2–3 tháng/năm. Kiểm tra
bằng công cụ:

```bash
python psr_targets.py --daytime                          # hôm nay
python psr_targets.py --daytime --date 2027-02-15        # ngày cụ thể
python psr_targets.py --daytime --min-sep 60             # chặt hơn
```

Kết quả cho **19/11/2026** (Mặt Trời RA = 234.6°):

| Pulsar | Giờ ban ngày | Cửa sổ tốt nhất (giờ VN) | Ghi chú |
|---|---|---|---|
| **B1929+10** | **6.3 h** | 11:05 → 17:20 | `alt_max` 89.8° — **mục tiêu ban ngày tốt nhất** |
| B1133+16 | 6.2 h | 05:55 → 12:00 | `alt_max` 85° |
| B0950+08 | 4.4 h | 05:55 → 10:15 | chính là mục tiêu #1, có cửa sổ **buổi sáng** |
| B1937+21 | 6.2 h | 11:15 → 17:20 | SNR quá thấp, chỉ để thử hệ thống |
| B0329+54, Vela, J0437, B1641, B1706 | 0 h | — | mùa này chỉ quan sát ban đêm |

Tháng 2/2027 thì ngược lại: B0329+54 có 4.3 h ban ngày, còn B0950+08 = 0 h (đúng
mùa ban đêm của nó — thuận lợi cho chiến dịch chính).

**Ba lưu ý thực chiến ban ngày:**
1. **Hiệu chuẩn lại mỗi 30–45 phút** — nhiệt độ thay đổi làm gain/bandpass trôi vài %.
2. Đừng trỏ Mặt Trời dù chỉ để "thử" — bão hoà/hỏng LNA (xem `04` §6).
3. Ban ngày **tốt hơn** cho mục tiêu gần thiên đỉnh: `T_sys` thấp vì ít spillover mặt
   đất. Một transit lúc 12h ở `alt 89°` có thể tốt hơn một quan sát ban đêm ở `alt 25°`.

*(Ở 408 MHz, ban ngày tệ hơn rõ rệt: tầng điện ly dày hơn (TEC ×5) → scintillation +
Faraday mạnh hơn, và RFI VHF/UHF ban ngày nhiều hơn. Ban ngày nên ưu tiên L-band.)*

---

## 8c. Chế độ **ngắm cố định** (để chảo một hướng, nguồn tự đi qua) — cách TNU làm

TNU đặt chảo một hướng rồi để tới sáng. Đây là **chế độ transit**, hoàn toàn hợp lệ —
nhưng phải hiểu nó đổi "thời gian quan sát" thành "thời gian hiệu dụng" như thế nào,
nếu không sẽ tưởng mình có 8 giờ dữ liệu trong khi thực chất chỉ có ~1 giờ.

**Công thức** (chùm Gauss, nguồn trôi với tốc độ `15.041°/h × cos δ`):

```
T_eff = 1.064 · HPBW / (15.041 · cos δ)      [giờ]
```

vì `SNR² ∝ ∫(độ lợi chùm) dt`, nên `T_eff` mới là con số đem vào công thức S/N.

| Hệ | HPBW @423 MHz | `T_eff` (B0950+08, δ = 7.9°) |
|---|---|---|
| 3.7 m (ta) | **13.4°** | **0.96 h** |
| 3.7 m @1.4 GHz | 4.0° | **0.28 h** (17 phút!) |
| 2.4 m (TNU) | 20.6° | 2.5 h — tức **cả buổi 2.5 h của họ ≈ đúng một lần transit** |

Đây là lý do **quyết định** phải dùng 423 MHz nếu muốn ngắm cố định: beam 4° ở L-band
chỉ cho 17 phút hữu ích mỗi đêm, còn beam 13.4° cho gần 1 giờ.

**Kết quả cho B0950+08, 423 MHz, `B` = 20 MHz, `T_sys` = 200 K, ngắm cố định:**

| Số đêm transit | SNR |
|---|---|
| 1 đêm | **5.9** |
| **2 đêm** | **8.3** ✅ ngưỡng phát hiện |
| 4 đêm | **11.8** |

So sánh: **track 2.5 h liên tục** cho SNR 10.9 → tracking tốt hơn 1.85× so với 1 transit.
Nhưng **2 đêm ngắm cố định (8.3) > 1 đêm track (10.9) về độ tin cậy**, vì có xác nhận
độc lập — và không cần ai thức canh.

**Quy tắc thực hành khi để chảo một hướng:**

1. Trỏ đúng **(az, el) lúc transit** (tính bằng `python psr_targets.py --transit`).
2. Ghi **UTC** lúc bắt đầu; đặt cửa sổ khai thác **transit ± 1.5 h** — phần còn lại
   của đêm chỉ là nhiễu, cộng vào sẽ **làm giảm** SNR.
3. **Trọng số theo độ lợi chùm**: `w(t) = exp(−4ln2·(θ(t)/HPBW)²)`. Đừng cộng đều.
4. Giờ transit **sớm đi ~4 phút mỗi ngày** → lịch phải cập nhật.
5. Kiểm tra mô hình chùm bằng **Mặt Trăng** (drift scan) trước chiến dịch; sai 1° ở
   423 MHz là mất ~3 % độ lợi, chấp nhận được, nhưng sai 5° thì mất 30 %.
6. Ban đêm nhiệt độ giảm → gain trôi: hiệu chuẩn lại bằng Cas A đầu và cuối buổi.

> Với chảo 3.7 m có motor + encoder, **nên track** nếu chạy được (10.9 so với 5.9). Chế
> độ ngắm cố định là **phương án dự phòng tốt** khi motor trục trặc, khi chỉ có 1 buổi
> ngắn, hoặc khi muốn "đặt rồi về".

Lệnh lập lịch:

```bash
python psr_targets.py --transit                 # giờ transit + T_eff + SNR/đêm hôm nay
python psr_targets.py --transit --date 2027-02-15 --bw 20
```

---

## 9. Rủi ro & giảm thiểu

| Rủi ro | Xác suất | Ảnh hưởng | Giảm thiểu |
|---|---|---|---|
| `T_sys` thực > 250 K | Trung bình | Thời gian ×3 | Đo ngay GĐ0; cải thiện chắn ground/feed |
| RFI 1.4 GHz quá mạnh | Trung bình | Mất độ nhạy | BPF chặt, quan sát đêm, A9 |
| Mất mẫu USB | **Cao** | Fold mất tín hiệu âm thầm | Đếm mẫu + injection test (G1) |
| Không mua được SDR | Trung bình | Trượt G2 | Phương án B/C; dùng thời gian cho HI |
| Trôi đồng hồ | Trung bình | Mất SNR khi fold dài | Dò lại `P` mỗi 1–2 h; GPSDO |
| Mưa/giông | Theo mùa | Mất đêm | Lịch dự phòng, bảo vệ thiết bị |
| Kỳ vọng sai (nghĩ dễ) | **Cao** | Mất tinh thần | Đọc `02` §4 trước khi bắt đầu |
| Sét đánh | Thấp | **Hỏng toàn bộ** | Chống sét Lan + tiếp địa + rút cáp khi giông |

---

## 10. Định nghĩa thành công

**Thành công tối thiểu (chắc chắn đạt):**
- 16/16 self-test PASS; `T_sys`, SEFD, beam đo được và công bố.
- Recorder + pipeline chạy trên dữ liệu thật; injection test PASS.
- Đính chính tài liệu; bộ tài liệu + code dùng được cho nhóm sau.

**Thành công mong đợi:**
- **Phát hiện B0950+08** (SNR ≥ 8, xác nhận 2 đêm, đúng pha) với `B = 40 MHz`.
- Đo `DM`, `W50`; nếu có 408 MHz: `α`.

**Thành công vượt:**
- 2–3 pulsar (thêm Vela), giant pulse Cua, `Ṗ` và `B` từ timing 6 tháng.

**Thành công "âm" vẫn có giá trị**: nếu không phát hiện được, ta có **upper limit
định lượng** (`S < X mJy` với `T_sys`, `B`, `t` ghi rõ) — đó là dữ liệu hiệu chuẩn
cho cộng đồng, và là bằng chứng trung thực về giới hạn của kính 3.7 m.

---

## 11. Việc làm ngay tuần này (checklist)

- [ ] 1. `cd "pulsar observation/code" && python selftest.py` → phải 16/16 PASS.
- [ ] 2. `python psr_pipeline.py` → xem `results/fig01_pipeline.png`; hiểu 4 panel.
- [ ] 3. `python psr_targets.py` và `--derived` → in ra, dán vào sổ tay quan sát.
- [ ] 4. Sửa `PROJECT_PLAN.md` §1/§3 theo `docs/02` §3 (SEFD + SNR).
- [ ] 5. Đo `T_sys` bằng Y-factor trên Cas A (1 buổi) — ghi vào metadata.
- [ ] 6. Khảo sát RFI 24 h → chọn cửa sổ giờ quan sát.
- [ ] 7. Viết `record_dynamic_spectrum()` + kiểm tra mất mẫu (2 h liên tục).
- [ ] 8. Làm injection test trên dữ liệu thật (task 1.4).
- [ ] 9. Xin báo giá SDR 10–56 MHz + BPF + LNA (3 nhà cung cấp).
- [ ] 10. Đặt lịch đêm quan sát B0950+08 vào **tháng 2**.

---

## 12. Kiến trúc code đề xuất (nối vào repo hiện có)

```
SKAO-TRT-rebuild/
├── skao_trt/
│   ├── sdr_wrapper.py        ← thêm read_samples_stream() + đếm mẫu
│   ├── record_data.py        ← thêm record_dynamic_spectrum()
│   ├── psr/                  ← MỚI: copy từ "pulsar observation/code/"
│   │   ├── core.py           (psr_core.py)
│   │   ├── sim.py            (psr_sim.py — dùng cho injection test)
│   │   ├── sensitivity.py
│   │   └── targets.py
│   └── apps/pulsar_app.py    ← MỚI: tab GUI (chọn mục tiêu → trỏ → ghi → fold)
└── tests/
    └── test_psr_core.py      ← chuyển từ selftest.py sang pytest
```

Nguyên tắc: `psr_core.py` **không import** gì từ `skao_trt` (thuần numpy) để có thể
kiểm thử độc lập — đó là lý do nó nằm riêng trong thư mục này.
