# 08 — Nghiên cứu khả thi: làm được gì về pulsar với thiết bị hiện có

Tài liệu này trả lời một câu: **với kính 3.7 m + RTL-SDR (423 MHz hoặc L-band
2.4 MHz), nhóm này có thể làm nghiên cứu pulsar gì, và cần gì để làm.**

Mọi tài liệu tham khảo dưới đây đã tra qua arXiv API (mã arXiv kèm theo để tra lại);
sách/handbook ghi rõ là sách. Không có trích dẫn tự đặt.

---

## 1. Năng lực thiết bị (các con số quyết định mọi kết luận)

| Đại lượng | 423 MHz | L-band 1420 MHz | Ghi chú |
|---|---|---|---|
| A_eff (η = 0.55) | 5.91 m² | 5.91 m² | D = 3.7 m |
| G | 2.14 mK/Jy | 2.14 mK/Jy | độc lập tần số |
| SEFD (T_sys 200 K) | 93 kJy | — | 61 kJy nếu T_sys 132 K |
| SEFD (T_sys 150 K) | 70 kJy | 70 kJy | |
| HPBW | **13.4°** | 4.0° | 1.22 λ/D |
| T_eff khi để chảo cố định | **~1 h** (δ ≈ 8°) | 0.28 h | quyết định "một đêm = một mục tiêu" |
| Độ phân giải DM (20 MHz) | ~0.25 (grid), ~1 thực tế | — | xem §1.2 |

### 1.1 Ngân sách SNR (công thức chuẩn, đã kiểm bằng mô phỏng)

```
SNR_fold = (S_mean / SEFD) · √(n_pol · B · t) · √(P / W)
```
(tương đương công thức Dewey với **peak flux**: `S_peak = S_mean·P/W`).

| Mục tiêu | S400 (ATNF) | S1400 (ATNF) | W50@1.4 | W@423 | **SNR 1 h @423, 40 MHz** | **SNR 1 h @L-band, 50 MHz** |
|---|---|---|---|---|---|---|
| **B0833-45 (Vela)** | 5,0 Jy | 1050 mJy | 1,7 ms | 3,4 ms | **138** | **44** |
| **B0329+54** | 1,5 Jy | 203 mJy | 6,6 ms | 9,5 ms | **71** | **12,4** |
| **B1641-45** | 0,38 Jy | 300 mJy | 8,0 ms | 180 ms ⚠ | **2,5** (tán xạ) | **13,2** |
| B1133+16 | 257 mJy | 20 mJy | 5,8 ms | 8,3 ms | 16,6 | 1,7 |
| B0950+08 | 400 mJy | 100 mJy | 8,6 ms | 12,3 ms | 9,8 | 3,1 |
| B1929+10 | 303 mJy | 29 mJy | 6,0 ms | 8,6 ms | 8,2 | 1,0 |
| B0531+21 (Cua) | 646 mJy | 14 mJy | 3,0 ms | 4,6 ms | 8,8 | 0,3 |

*(Tính bằng `psr_sensitivity.snr_fold`, n_pol = 1; SEFD 70 kJy @423 (T_sys 150 K) và
35,8 kJy @L-band (từ G/T = 13,55 dB/K của datasheet RTP37). W@423 tính theo mô hình
trong `psr_targets.w50_at` — xem `docs/02` §4.0.)*

**ĐÍNH CHÍNH (2026-11):** bảng trước đây dùng S400/S1400 **chép tay, sai tới ×7**
(B0329+54 ghi 200 mJy thay vì 1500; Vela 700 thay vì 5000) nên kết luận "chỉ B0950+08
làm được" là **sai**. Số đúng lấy từ ATNF psrcat v2.9.0:

**Kết luận mới:** **Vela, B0329+54, B1641-45 là 3 mục tiêu dễ nhất** —
Vela đạt SNR 8 trong **~3 phút** (L-band, 50 MHz) hoặc ~2 phút (423 MHz, 40 MHz);
B0329+54 và B1641-45 trong **~25 phút**. B0950+08 tụt xuống hạng 5 (cần ~6,5 h ở
L-band, ~40 phút ở 423 MHz). Lưu ý B1641-45 (DM 479) **không quan sát được ở 423 MHz**
vì tán xạ 180 ms, nhưng tốt ở L-band.

### 1.2 Sai số đo DM (quyết định đo được gì về môi trường liên sao)

`δDM ≈ W50 / (K·Δ(1/f²))`. Với 20 MHz tại 423 MHz, `K·Δ(1/f²) = 2.19 ms` trên
1 đơn vị DM:

| Pulsar | W50 | δDM (một băng 20 MHz) | Đo được biến thiên DM? |
|---|---|---|---|
| Cua (giant pulse) | 0.8 ms | ~0.4 (đo thực tế 56.71 ± 0.57) | không (quá ngắn) |
| B0329+54 | 8.2 ms | ~4 | không |
| B0950+08 | 25 ms | ~11 | **không** |

→ **Không** làm được "DM variations" kiểu Lam & Cordes; chỉ đo DM một lần để
**xác nhận đúng nguồn** (sai số vài đơn vị là đủ phân biệt).

---

## 2. Danh mục nghiên cứu — xếp theo mức khả thi

### Nhóm A — LÀM ĐƯỢC, đúng với thiết bị (nên làm trước)

| # | Đề tài | Cần đo gì | Thời gian | SNR | Tài liệu |
|---|---|---|---|---|---|
| A1 | **Xác nhận & đo tham số 3–4 pulsar sáng** (DM, P, W50, profile 423 MHz) | 1 file/đêm, fold tại P | 1 đêm/mục tiêu | 6.1/h (B0950) | Lorimer & Kramer 2005 (sách), Bilous+2015 (arXiv:1511.01767) |
| A2 | **So sánh profile 423 MHz với LOFAR 100–200 MHz** — profile giãn/trễ theo tần số, kiểm tra hiệu ứng tán sắc trong profile | profile chuẩn hoá, W10/W50, độ bất đối xứng | 1–2 đêm | 6.1/h | Bilous+2015 (1511.01767), Noutsos+2015 (1501.03312) |
| A3 | **Theo dõi biến thiên cường độ giữa các đêm** (scintillation ISS + biến thiên nội tại) | flux tương đối so với nguồn chuẩn (Cas A) | 8–10 đêm rải 2–3 tháng | ≥ 6/đêm | Wang & Wang 2023 (2301.07367), Bhat+1998 (astro-ph/9810354) |
| A4 | **Kiểm chứng hệ thống & hiệu chuẩn** (T_sys Y-factor, gain, độ ổn định bandpass, RFI 24 h) | công suất nguồn chuẩn, phổ nhiễu | 2–3 đêm | — | Nita & Gary 2010 (1005.4371), Taylor+2018 (1808.10365) |
| A5 | **Nguồn continuum** (Cas A, Cyg A, Mặt Trăng, Mặt Trời) — không phải pulsar nhưng là "đối chứng dương" cho toàn chuỗi | độ sáng theo thời gian, độ rộng chùm tia | vài đêm | rất cao | (docs/04 trong repo) |

### Nhóm B — CÓ ĐIỀU KIỆN (cần nhiều đêm hoặc may mắn)

| # | Đề tài | Điều kiện | Thời gian | Tài liệu |
|---|---|---|---|---|
| B1 | **Cộng dồn nhiều đêm để phát hiện pulsar yếu hơn** (B1929+10, B1133+16) | SNR từng đêm ≥ 1.5, cộng 10–20 đêm → SNR ≥ 7 | 10–20 đêm/mục tiêu | Lorimer & Kramer 2005 |
| B2 | **Tìm giant pulse của Cua ở 423 MHz** | cần GP rất mạnh: SNR ≈ (S_GP/93 kJy)·√(B·W); GP điển hình 500 Jy → **SNR ~1**; chỉ GP > 5 kJy mới thấy. Tỉ lệ thấp | 5–10 đêm thử | Karuppusamy+2010 (1004.2803), Doskoch+2024 (2407.15996), Jones 2015 GAVRT (1507.03864) |
| B3 | **Tìm xung đơn kiểu RRAT trong vài trường** (1 chùm tia 13°) | chỉ bắt được xung rất mạnh; năng suất thấp nhưng là bài toán "search" thật | 20+ đêm | McLaughlin+2006 (astro-ph/0511587), Cordes & McLaughlin 2003 (astro-ph/0304364), Golpayegani+2019 GBTrans (1905.00980) |
| B4 | **Nulling fraction** của một pulsar sáng | cần SNR mỗi chu kỳ ≥ 8 → **không** khả thi với B0950; chỉ khả thi nếu có kính lớn hơn | — | Kaplan+2018 (1801.09598), Anumarlapudi+2023 (2301.13258) |
| B5 | **Dò chu kỳ mù cho nguồn chưa biết** (sau khi có M3) | cần M2.5 đo được completeness; vẫn giới hạn bởi độ nhạy | — | Morello+2014 SPINN (1406.3627), Lin+2020 (2007.14843) |

### Nhóm C — KHÔNG KHẢ THI (ghi để không mất thời gian)

| Đề tài | Vì sao không |
|---|---|
| Timing chính xác / PTA / sao xung đôi | cần máy thu băng rộng, ổn định clock, nhiều năm, kính lớn |
| Đo phân cực, RM, hình học phát xạ | cần 2 phân cực tuyến tính trực giao + hiệu chuẩn; RTL-SDR đơn kênh |
| Phát hiện **pulsar mới** | độ nhạy thấp hơn ~10²–10³ lần so với survey chuyên nghiệp |
| FRB | cần FoM lớn hơn nhiều + trường nhìn rộng (Lorimer+2007, 0709.4301) |
| Single-pulse energetics / jitter | cần SNR mỗi xung cao (Mickaliger+2018 1807.00143; Burke-Spolaor+2012 1203.6068) |
| MSP, pulsar trong quần tinh | SNR << 1 |

---

## 3. Tài liệu tham khảo theo chủ đề (đã tra)

### Nền tảng
- **Lorimer & Kramer, _Handbook of Pulsar Astronomy_** (Cambridge, 2005) — công thức
  ngân sách SNR, quy trình fold, DM, hiệu chỉnh barycentric. **Sách.**
- Lyne & Graham-Smith, _Pulsar Astronomy_ (Cambridge) — **sách**.

### Pulsar băng tần thấp (so sánh trực tiếp với 423 MHz)
- Bilous+2015, *A LOFAR census of non-recycled pulsars* — arXiv:1511.01767
- Noutsos+2015, *Pulsar polarisation below 200 MHz* — arXiv:1501.03312
- Bondonneau+2020, *A census of the pulsar population observed with the international
  LOFAR station FR606* — arXiv:2003.01071 (một trạm đơn, gần giống mô hình của ta)
- Kondratiev+2012, *Pulsar emission at the bottom end of the electromagnetic spectrum*
  — arXiv:1210.6994

### Giant pulse
- Karuppusamy+2010, *Giant pulses from the Crab pulsar: a wide-band study* — arXiv:1004.2803
- Doskoch+2024, *A Statistical Analysis of Crab Pulsar Giant Pulse Rates* — arXiv:2407.15996
- Petrova 2006, *Nature of giant pulses in radio pulsars* — arXiv:astro-ph/0605154
- Ershov & Kuzmin 2006, *Giant Pulses in PSR J1752+2359* — arXiv:astro-ph/0605086
- Jones 2015, *Observations of Radio Giant Pulses with GAVRT* — arXiv:1507.03864
  (kính 34 m dùng cho giáo dục — tiền lệ gần nhất về "kính vừa + giant pulse")

### Xung đơn, RRAT, tìm kiếm
- Cordes & McLaughlin 2003, *Searches for Fast Radio Transients* — arXiv:astro-ph/0304364
  (công thức figure-of-merit cho xung đơn — dùng để biết cần bao nhiêu độ nhạy)
- McLaughlin+2006, *Transient radio bursts from rotating neutron stars* — arXiv:astro-ph/0511587
- Mickaliger+2018, *A Study of Single Pulses in the Parkes Multibeam Pulsar Survey* — arXiv:1807.00143
- Burke-Spolaor+2012, *HTRU V: single-pulse energetics* — arXiv:1203.6068
- Golpayegani+2019, *GBTrans: a commensal search with the Green Bank 20 m* — arXiv:1905.00980

### Nulling / biến đổi phát xạ
- Kaplan+2018, *A Gaussian Mixture Model for Nulling Pulsars* — arXiv:1801.09598
- Anumarlapudi+2023, *A Pilot Study of Nulling in 22 Pulsars* — arXiv:2301.13258

### Cường độ & scintillation
- Wang & Wang 2023, *Study of pulsar flux density and its variability with Parkes data* — arXiv:2301.07367
- Bhat+1998, *Long-Term Scintillation Studies of Pulsars: I* — arXiv:astro-ph/9810354

### DM & môi trường liên sao (để biết vì sao *không* làm được)
- Lam & Cordes 2015, *Systematic and Stochastic Variations in Pulsar DMs* — arXiv:1512.02203
- Cordes & Shannon 2015, *Frequency-Dependent DMs* — arXiv:1503.08491

### Kỹ thuật xử lý (dùng cho pipeline M2–M3)
- Barsdell+2012, *Accelerating incoherent dedispersion* — arXiv:1201.5380
- Zackay & Ofek 2014, *An accurate and efficient algorithm for detection of radio
  bursts with an unknown dispersion measure* — arXiv:1411.5373
- Nita & Gary 2010, *The Generalized Spectral Kurtosis Estimator* — arXiv:1005.4371
- Taylor+2018, *Spectral Kurtosis Based RFI Mitigation for CHIME* — arXiv:1808.10365
- Purver+2021, *Removal and replacement of interference in tied-array pulsar
  observations using spectral kurtosis* — arXiv:2111.14225

### Phân loại ứng viên (cho M3)
- Morello+2014, *SPINN* — arXiv:1406.3627
- Lin+2020, *Pulsar Candidate Sifting Using Multi-input CNN* — arXiv:2007.14843

### Giáo dục / cộng đồng (mô hình tổ chức)
- Blumer+2019, *The Pulsar Search Collaboratory* — arXiv:1909.05104

---

## 4. Dữ liệu công khai để luyện phương pháp (không cần phần cứng)

Đây là "fallback" mạnh nhất: **làm khoa học thật trên dữ liệu người khác thu**.

| Nguồn | Dùng để | Đã dùng trong repo? |
|---|---|---|
| GREENBURST (Arecibo) | file `.fil` thật, nhiều DM, có RFI | ✅ `data/B0329+54.fil` |
| Dwingeloo 25 m (giant pulse Cua, IQ thô) | kiểm chứng "từ dây vào", channelize | ✅ `data/iq/crab-giantpulse.sigmf-data` |
| IQRM corpus (Crab cutout, B1828, "empty") | corpus dữ liệu xấu | ✅ `data/stress/` |
| EPN (European Pulsar Network) profiles | so sánh profile 423 MHz ta đo với profile chuẩn đa tần số | chưa |
| ATNF Pulsar Catalogue | tham chiếu DM/P/flux, đánh giá "gợi ý nhận dạng" | ✅ `psr_targets.py` |
| LOFAR/FR606 census (Bondonneau+2020) | so sánh độ nhạy & profile ở tần số thấp | chưa |

---

## 5. Ba dự án nên chọn (12 tuần), theo thứ tự

**D1 — "Pulsar 423 MHz đầu tiên của nhóm" (4–6 tuần)**
Mục tiêu: phát hiện B0950+08 với SNR ≥ 8 (cần 20 MHz + 2.5 h, hoặc 2 đêm × 2.5 h ở
10 MHz), đo DM & P, xuất profile so với LOFAR.
Điều kiện: BPF 380–450 MHz + SDR ≥ 10 MHz (không có thì SNR 2.4 → không đạt).
Sản phẩm: 1 báo cáo + profile + bằng chứng tái lập 2 đêm.

**D2 — "Theo dõi biến thiên cường độ B0950+08" (8–10 tuần, chạy song song)**
Mục tiêu: 8–10 đêm rải 2–3 tháng, đo flux tương đối so với Cas A; so với thang thời
gian scintillation dự đoán. Đây là nghiên cứu **thật** làm được với thiết bị này.

**D3 — "Phương pháp tìm kiếm" (không cần phần cứng)**
Dùng dữ liệu công khai + injection–recovery (M2.5) để **đo giới hạn phát hiện** của
một kính nhỏ; công bố dạng báo cáo kỹ thuật/khóa luận. Đây là đóng góp trung thực
nhất mà 3.7 m có thể làm về "tìm pulsar".

---

## 6. Phần mềm cần bổ sung để làm được các đề tài trên

| Đề tài | Cần gì | Mốc |
|---|---|---|
| D1 | hồ sơ trạm/kính + dò DM 2 tầng + báo cáo chuẩn | M1, M2 |
| D1 | **đo profile & so sánh** (xuất profile chuẩn hoá, W10/W50) | M3 |
| D2 | flux tương đối + hiệu chuẩn bandpass 600 s + cộng dồn đêm | M2, M4, `stack` |
| D3 | injection–recovery + `capability_matrix.md` | **M2.5** |
| B2 (giant pulse) | tìm xung đơn nhạy + FoM theo Cordes & McLaughlin | M2, M3 |
| A4 | đo T_sys (Y-factor), RFI 24 h, `adc_clip_frac` | M1 |

---

## 7. Giới hạn trung thực (phải nói trước khi bắt đầu)

1. **Không có khả năng phát hiện pulsar mới** với kính 3.7 m; mọi tuyên bố kiểu đó
   cần đài lớn xác nhận.
2. **Một mục tiêu mỗi đêm** (T_eff ~1 h @423); không quét trời.
3. Chỉ **1 pulsar** (B0950+08) gần đạt SNR 8 trong một đêm 2.5 h với 20 MHz
   (6.1 × √2.5 = 9.6); các mục tiêu khác cần 10–20 đêm. Với 2.4 MHz hiện tại thì
   **không** mục tiêu nào đạt trong một đêm.
4. Giant pulse Cua: chỉ thấy khi GP **rất** mạnh (SNR ~1 với GP điển hình 500 Jy) —
   coi là "thử vận may", không phải kế hoạch.
5. Không đo được biến thiên DM, không đo phân cực, không timing chính xác.
