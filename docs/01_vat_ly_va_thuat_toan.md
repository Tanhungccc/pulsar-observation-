# 01 — Vật lý tín hiệu pulsar & danh mục thuật toán phát hiện

*Tài liệu nội bộ chương trình **Pulsar Observation** — kính POAM RTP-3.7 (TP.HCM).*
*Mọi con số trong tài liệu này lấy từ `code/psr_pipeline.py` và `code/selftest.py`
(chạy lại được, xem §6).*

---

## 1. Tín hiệu pulsar trông như thế nào

Pulsar = sao neutron quay, phát xạ vô tuyến thành **chùm hẹp** gắn với trục từ.
Mỗi lần chùm quét qua Trái Đất ta nhận một **xung**; chu kỳ lặp lại chính là chu kỳ
quay `P` (1.6 ms → vài giây). Vì chùm hẹp, xung chỉ chiếm một phần nhỏ chu kỳ:

| Đại lượng | Ký hiệu | Giá trị điển hình | Ý nghĩa thực chiến |
|---|---|---|---|
| Chu kỳ | `P` | 0.033 s (Cua) … 1.19 s (B1133+16) | quyết định số xung tích luỹ được |
| Độ rộng xung | `W50` | 0.5–30 ms | quyết định "duty cycle" `W/P` = 0.5–10 % |
| Tốc độ đổi chu kỳ | `Ṗ` | 1e-19 … 4e-13 | cho biết tuổi, từ trường (xem `03`) |
| Thông lượng | `S` | 3 mJy … 1 Jy @1.4 GHz | quyết định có thấy hay không |
| Chỉ số phổ | `α` (`S∝ν^α`) | −1.6 (thường), −3 (Cua) | **quan sát 400 MHz lợi 5–10 lần** so với 1.4 GHz |
| DM | `DM` | 2.6 … 475 pc cm⁻³ | quyết định phải khử tán sắc hay không |

Điểm cực kỳ quan trọng: **năng lượng pulsar nhỏ hơn nguồn continuum rất nhiều**.
Với chảo 3.7 m, 1 Jy cho nhiệt độ ăng-ten 2.14 mK. Cas A (2700 Jy) cho 5.8 K;
một pulsar 25 mJy cho **0.054 mK** — nhỏ hơn 100 000 lần. Vì thế pulsar không thể
"nhìn thấy" trên phổ như vạch HI, mà phải **tích luỹ theo pha** (folding) hàng giờ.

---

## 2. Những gì xảy ra trên đường truyền (và phải sửa)

### 2.1 Tán sắc — hiệu ứng lớn nhất

Plasma liên sao có chiết suất phụ thuộc tần số → xung tần số thấp đến **trễ** hơn:

```
t(ν) = K_DM · DM / ν²        K_DM = 4.148808×10³   [s, ν theo MHz]
```

Với `DM` tính bằng pc cm⁻³. Các hệ quả định lượng (dùng đúng trong code):

| Đại lượng | Công thức | DM = 27 | DM = 68 | DM = 475 |
|---|---|---|---|---|
| Trễ tuyệt đối @1.4 GHz | `K·DM/ν²` | 57 ms | 144 ms | 1.0 s |
| Trải trên dải 64 MHz @1.4 GHz | `8.3e-3·DM·B/ν³` | **5.1 ms** | **12.9 ms** | **90.6 ms** |
| Trải trên dải 2.4 MHz @1.4 GHz | nt | 0.19 ms | 0.48 ms | 3.4 ms |
| Trải trên dải 2.4 MHz @408 MHz | nt | 2.5 ms | 6.4 ms | 44 ms |
| Trải **trong 1 kênh** 1 MHz @1.4 GHz | nt | 0.08 ms | 0.20 ms | 1.4 ms |

**Đọc bảng này để quyết định**: nếu trải-dải ≲ `W50/4` thì **không cần** khử tán sắc.
Đó chính là trường hợp RTL-SDR hiện có (2.4 MHz) với pulsar DM thấp — may mắn.
Nhưng khi nâng băng thông lên 40–64 MHz (điều kiện bắt buộc để đủ độ nhạy), khử
tán sắc trở thành **bắt buộc** với mọi pulsar DM > 30.

### 2.2 Tán xạ (scattering) — giới hạn cứng của độ rộng xung

Tán xạ đa đường làm xung có **đuôi hàm mũ** dài, `τ_sc ∝ ν^-4.4`. Với pulsar DM lớn
ở tần số thấp, `τ_sc` có thể vượt cả chu kỳ. Hệ quả: **không phải cứ xuống tần số
thấp là tốt hơn** — thông lượng tăng `ν^-1.6` nhưng độ rộng xung tăng nhanh hơn.

### 2.3 Nhấp nháy (scintillation) — cái bẫy "hôm nay không thấy"

Dải tần nhấp nháy `Δν_d` và thang thời gian `Δt_d` của pulsar thay đổi theo hướng
nhìn và thời gian. Có đêm tín hiệu mất hoàn toàn vì ta rơi vào "nút" nhấp nháy.
→ **Luôn quan sát lặp lại ít nhất 3 đêm khác nhau** trước khi kết luận "không thấy".

### 2.4 Hiệu chỉnh quỹ đạo (barycentric)

Trái Đất quay quanh Mặt Trời ±30 km/s. Nếu fold 6 giờ mà không hiệu chỉnh về khối
tâm Hệ Mặt Trời, pha trôi có thể tới vài chục chu kỳ với pulsar nhanh. Với pulsar
chậm (`P` > 0.2 s) và tích luỹ < 1 giờ, có thể bỏ qua **nếu** chấp nhận mất SNR;
muốn làm timing thật thì **bắt buộc** dùng `astropy` + `TEMPO2/PINT`.

### 2.5 Tán sắc Faraday / RM

Nếu feed có 2 phân cực: mặt phẳng phân cực quay `Δψ = RM·λ²`. Đo RM → từ trường
dọc theo tia nhìn. Thiết bị hiện tại (1 phân cực) **chưa làm được** — xem `03`.

---

## 3. Mô hình toán học của bài toán

Dữ liệu thô là **phổ động** (dynamic spectrum) `D[ν, t]`: công suất tại kênh tần số
`ν` và mẫu thời gian `t`. Mô hình:

```
D[ν,t] = G(ν)·[ T_sys + T_A·Σ_k g( t − t_k − K·DM/ν² ; W ) ] + n(ν,t)
```

- `g` = dạng xung (Gauss/Lorentz + đuôi tán xạ), `t_k = t_0 + k·P`
- `n` = nhiễu radiometer (Gauss, độ lệch chuẩn `T_sys/√(B·τ)`)
- `G(ν)` = bandpass của hệ (phải chia đi — bước A1)

Ba chế độ xử lý, ứng với ba mục tiêu khác nhau:

| Chế độ | Biết trước | Mục đích | Độ khó |
|---|---|---|---|
| **Fold** (định hướng) | P, DM từ ATNF | hồ sơ xung, SNR, timing | dễ |
| **Search** (mù) | không | tìm P và DM | khó |
| **Single-pulse** | P, DM | giant pulse, microstructure, nulling | trung bình |

---

## 4. Danh mục thuật toán

Mã `A1…A13` dùng thống nhất trong code (`code/psr_core.py`) và trong kế hoạch (`05`).

### A1 — Chuẩn hoá bandpass & chia kênh

- **Việc**: `D[ν,t]` từ IQ: FFT từng block → công suất; chia mỗi kênh cho đường nền
  trơn của nó (median theo thời gian).
- **Vì sao**: nếu không, bandpass của LNA/filter (biến thiên 3–10 dB) sẽ tạo "vạch
  giả" và làm hỏng mọi bước sau.
- **Cảnh báo**: chuẩn hoá bandpass **xoá luôn RFI băng hẹp dạng nền nâng cao**. Do đó
  phải **phát hiện kênh hỏng trên dữ liệu THÔ trước** rồi mới chuẩn hoá (lỗi này đã
  xảy ra và được sửa trong `psr_pipeline.py`).

### A2 — Khử tán sắc KHÔNG kết hợp (incoherent dedispersion)

Cho mỗi kênh một độ dịch nguyên mẫu:

```
shift(ν) = round( [t(ν) − t(ν_ref)] / Δt_sample )
D_dd[t]  = (1/N_ν) Σ_ν  D[ν, t + shift(ν)]        (ν_ref = kênh tần số cao nhất)
```

Độ phân giải còn lại = trải trong 1 kênh (bảng §2.1). **Rẻ, chạy được trên CPU
thường, đây là lựa chọn đúng cho RTP-3.7.**

Giả mã:

```
for dm in dm_trials:                     # A8 quyết định lưới này
    out = zeros(ntime - max_shift)
    for i, nu in enumerate(freqs):
        s = round(K*dm*(1/nu**2 - 1/nu_max**2)/tsamp)
        out += D[i, s : s+len(out)]
    yield out/len(freqs)
```

### A3 — Khử tán sắc KẾT HỢP (coherent)

Nhân phổ phức của một block IQ dài với hàm pha:

```
H(f) = exp[ +j·2π·K·DM·(1/f − 1/f_0)·(N/fs) ]
```

- **Ưu**: giữ được cấu trúc dưới 1 µs (giant pulse, microstructure) — điều A2 không
  làm được vì A2 bị chặn bởi độ rộng kênh.
- **Nhược**: cần đọc IQ **liên tục, không mất mẫu** và block dài (≥ 2^20 mẫu).
  RTL-SDR đọc theo chunk qua USB, rất dễ mất mẫu giữa các lần đọc → **phải kiểm tra
  bằng bộ đếm mẫu** trước khi tin. Trong kế hoạch: chỉ bật A3 khi đã có SDR stream
  liên tục (Pluto+/USRP) và đã xác nhận không mất mẫu.

### A4 — Fold theo chu kỳ (epoch folding)

```
pha(t)  = (t − t_0)/P − 0.5·Ṗ·(t − t_0)²/P²
hồ sơ   = trung bình D_dd[t] theo bin pha (nbin)
```

Ba lỗi thực chiến (đã mắc và đã sửa — ghi lại để nhóm không lặp):

1. **Xung nằm vắt qua pha 0** → lọc khớp dạng cumsum thẳng bị chia đôi, SNR tụt ~2×.
   → Luôn dùng cửa sổ **vòng** (circular) khi đo SNR hồ sơ.
2. **`nbin` quá thô** → SNR bị lượng tử hoá theo pha, đường cong DM xuất hiện "đỉnh
   giả". Quy tắc: `nbin ≥ 4·P/W50` (với P/W = 60 phải dùng ≥ 240 bin).
3. **`t_0` khác nhau giữa các lần thử DM** → pha lệch → so sánh SNR không công bằng.
   Trục thời gian **sau** A2 là thời gian phát xạ (≈ `j·Δt`), nên dùng cùng `t_0 = 0`
   cho mọi lần thử.

### A4b — Tinh chỉnh chu kỳ (bắt buộc, hay bị bỏ qua)

Độ phân giải tần số của FFT là `1/T_obs`, tương ứng sai số chu kỳ `ΔP/P ≈ P/T_obs`.
Với `P = 0.71 s`, `T = 90 s` → `ΔP ≈ 0.4 %` → tích pha trôi **0.4 chu kỳ** trong
90 s → hồ sơ nhoè hoàn toàn.

Thuật toán: quét `f` trong `±1/T` với bước đủ mịn (trôi pha < 1 bin/vòng), lặp lại
3 tầng quanh đỉnh (bracket → zoom → zoom).

Kết quả đo được trong mô phỏng: `P_FFT` lệch `0.4 %` (không dùng được) → sau 3 tầng
tinh chỉnh còn **6.8 ppm** (`89.3274 ms` vs `89.3280 ms`).

### A5 — Tìm chu kỳ bằng FFT + cộng hài

```
P(f)      = |FFT( D_dd(t) − mean )|²
score(f)  = Σ_{k=1..K} P(k·f) / K          (harmonic summing, K = 4…8)
```

Đây là cách **sinh ứng viên** chuẩn (PRESTO dùng tới 32 hài). Nhưng:

> **Bài học đo được**: trong lần chạy mẫu, ứng viên **hạng 1 của FFT là đỉnh nhiễu**
> (`27.99 Hz = 2.5·f0`), còn `f0` thật chỉ hạng 3. Cộng hài khuếch đại cả nhiễu.
> **FFT không bao giờ là kết luận** — phải kiểm chứng bằng fold:

| Ứng viên FFT | P (ms) | SNR sau fold |
|---|---|---|
| #1 (27.99 Hz) | 35.73 | **7.5** ✗ |
| #2 (33.59 Hz) | 29.78 | 13.9 |
| **#3 = f0 thật (11.19 Hz)** | **89.33** | **27.6** ✓ |
| #4 | 59.55 | 11.8 |

Quy trình đúng: FFT sinh 5–10 ứng viên → tinh chỉnh chu kỳ từng ứng viên → fold →
**xếp hạng lại theo SNR**.

### A6 — FFA (Fast Folding Algorithm)

Quét chu kỳ bằng cách fold **mọi** chu kỳ trong một dải bằng cấu trúc cây, độ phức
tạp `O(N log N)`. Ưu điểm so với FFT: **nhạy hơn với pulsar có duty cycle lớn** và
không bị "rò rỉ" do phổ hài. PRESTO có `ffa2`. Chưa cần cho giai đoạn đầu (ta làm
quan sát định hướng, P đã biết) — xếp vào giai đoạn 4.

### A7 — Xung đơn / giant pulse (lọc khớp boxcar)

```
z(t) = [Σ_{i<t..t+w} (x − median)] / (σ_MAD · √w)      → max theo w và t
```

Dùng cho: giant pulse của Cua, nulling, microstructure. Ở đây **khử tán sắc kết hợp
(A3) mới giữ được độ rộng µs**; với A2, xung bị làm rộng tới `trải/kênh`.

### A8 — Lưới thử DM (DM plan)

Không quét DM dày vô ích. Bước lưới hợp lý: lượng DM làm trải thêm ≈ `W/4`:

```
ΔDM_trial ≈ (W/4) / (8.3e-3 · B_MHz / ν_GHz³)
```

Với `W = 3 ms`, `B = 64 MHz`, `ν = 1.4 GHz` → `ΔDM ≈ 4`. Quét 0–500 = 125 lần thử
(chấp nhận được). Nếu quét dày hơn chỉ tốn CPU mà không tăng độ nhạy.

### A9 — Khử RFI (3 tầng, rẻ, hiệu quả)

| Tầng | Phát hiện | Cách xử lý | Đo được trong mô phỏng |
|---|---|---|---|
| Zero-DM | xung xuất hiện **đồng thời mọi kênh** (tia lửa, máy bay) | thay cả cột bằng nền | cắt 32/480 000 mẫu (0.01 %) |
| Kênh hỏng | công suất trung bình kênh lệch > 4σ | bỏ kênh | bỏ 4/64 kênh |
| Spectral Kurtosis | `SK = (N+1)/(N−1)·[N·ΣP²/(ΣP)² − 1]`, 1 = nhiễu, >1 = RFI | bỏ kênh/thời đoạn | (có hàm, chưa bật) |

SKAO-TRT gốc không có tầng nào trong số này — đây là phần **phải thêm**.

### A10 — Đo SNR và độ rộng xung

`SNR = (tổng on-pulse − nền) / (σ_nền · √w)`, tối ưu theo `w` (boxcar) và theo vị trí.

> **Cảnh báo định lượng**: vì lấy **max** trên mọi vị trí và mọi độ rộng, với dữ liệu
> **chỉ có nhiễu** thuật toán vẫn trả về **SNR ≈ 3.5** (đo được trong `selftest.py`).
> ⇒ **Ngưỡng phát hiện phải là SNR ≥ 6–8**, không phải 3. Muốn chắc chắn hơn: lặp lại
> ở đêm khác, và kiểm tra tín hiệu **xuất hiện đúng pha** ở cả hai lần.

### A11a — Đo DM bằng quét thử

Quét DM, mỗi lần fold, lấy SNR lớn nhất. **Độ phân giải** (không phải độ chính xác
thống kê):

```
σ_DM ≈ (W50/2) / (độ trễ mỗi đơn vị DM) = (W50/2)/(8.3e-3·B/ν³)
```

Với `W50 = 3 ms`, `B = 64 MHz` → `σ_DM ≈ ±11`. Đo được trong mô phỏng: **77 ± 11**
(giá trị thật 67.9) — đúng trong sai số, nhưng **không dùng để công bố DM**.

### A11b — Đo DM bằng độ trễ giữa các dải con (chính xác hơn nhiều)

Không cần biết DM trước:

1. Cắt dải thành 4 dải con, **fold riêng từng dải con** theo `P`.
2. Đo **trọng tâm** xung của từng dải con (trọng tâm bảo toàn khi chập với hạt nhân
   trải tán sắc → không bị thiên lệch, khác với đo đỉnh).
3. Khớp `t(ν) − t(ν_ref) = K·DM·(1/ν² − 1/ν_ref²)`.

Kết quả mô phỏng: **67.25 ± 2.0** (thật 67.94) — tốt hơn A11a **5 lần**. Điều kiện:
SNR mỗi dải con ≳ 10. Đây là phương pháp nên dùng để **đo DM** khi đã phát hiện.

### A12 — Timing (đo TOA, mô hình hoá)

`TOA` = thời điểm đến của một mốc pha (vd. đỉnh xung), hiệu chỉnh về barycentre.
Chuỗi TOA qua nhiều tháng → fit `P, Ṗ, ν̇, vị trí, thị sai, quỹ đạo sao đôi`.
Cần: đồng hồ ổn định (TCXO ±0.5 ppm đủ cho 1–2 giờ; **GPSDO cần cho timing dài**),
và template ổn định.

### A13 — Phân cực / RM

Cần feed 2 phân cực + hiệu chuẩn phân cực. Cho: hình học từ trường (RVM), độ cao
vùng phát xạ, `RM = 0.81∫ B_∥ n_e dl`. **Ngoài khả năng thiết bị hiện tại** — giai
đoạn nâng cấp.

---

## 5. Ma trận: thuật toán ↔ điều kiện ↔ trạng thái trong repo

| Mã | Cần dữ liệu gì | Có trong `code/` | Chạy được với RTL-SDR hiện có? |
|---|---|---|---|
| A1 | phổ động | ✅ `channelize`, `bandpass_normalize` | ✅ |
| A2 | phổ động | ✅ `dedisperse` | ✅ |
| A3 | **IQ liên tục** | ✅ `coherent_filter_taps` (chưa nối vào pipeline) | ⚠ cần kiểm tra mất mẫu |
| A4 | chuỗi đã khử tán sắc | ✅ `fold` | ✅ |
| A4b | như trên | ✅ `refine_period` | ✅ |
| A5 | như trên | ✅ `fft_search` + kiểm chứng fold trong pipeline | ✅ |
| A6 | như trên | ❌ (dùng PRESTO `ffa2`) | ✅ (CPU) |
| A7 | chuỗi độ phân giải µs | ✅ `boxcar_snr` | ⚠ chỉ sau A3 |
| A8 | — | ✅ công thức trong `02` | ✅ |
| A9 | phổ động | ✅ `zero_dm_excise`, `mask_bad_channels`, `spectral_kurtosis` | ✅ |
| A10 | hồ sơ | ✅ `profile_snr` (cửa sổ vòng) | ✅ |
| A11a | phổ động | ✅ `dedisperse_stack` | ✅ |
| A11b | phổ động | ✅ `dm_from_subbands` | ✅ |
| A12 | TOA nhiều tháng | ❌ (dùng `PINT`/`TEMPO2`) | ⚠ cần GPSDO |
| A13 | 2 phân cực | ❌ | ❌ |

---

## 6. Kết quả kiểm chứng (chạy lại được)

`python code/selftest.py` → **16/16 PASS**, gồm các kiểm tra vật lý (SEFD, beam,
trễ DM) và kiểm tra thuật toán (khử tán sắc đặt xung đúng chỗ, tinh chỉnh chu kỳ
< 100 ppm, DM dải con < 8 %, pipeline end-to-end).

`python code/psr_pipeline.py` (kịch bản: pulsar kiểu Vela `P = 89.3 ms`, `W50 = 3 ms`,
`DM = 67.9`, `B = 64 MHz`, 64 kênh, 120 s, SNR đặt 30):

| Bước | Kết quả đo |
|---|---|
| A9 RFI | bỏ 4/64 kênh, cắt 0.01 % mẫu |
| A10 fold **chưa** khử tán sắc | SNR **11.1** |
| A10 fold **sau** khử tán sắc | SNR **21.5** (×1.9) |
| A11a quét DM | **77 ± 11** (thật 67.9) |
| A11b trễ dải con | **67.25 ± 2.0** (sai 1 %) |
| A5 FFT | hạng 1 **sai**, f0 ở hạng 3 |
| A4b tinh chỉnh chu kỳ | **89.3274 ms**, lệch **−6.8 ppm** |
| SNR cuối | **27.6** (đặt 30) |

Thí nghiệm phụ (cùng `B = 64 MHz`, 60 s, SNR đặt 25) — **khi nào buộc phải khử tán sắc**:

| DM | Trải toàn dải | Trải/kênh | SNR không khử | SNR có khử | Kết luận |
|---|---|---|---|---|---|
| 26.8 | 5.1 ms | 0.081 ms | 18.5 | 16.7 | không cần |
| 100 | 19.1 ms | 0.302 ms | 15.5 | 19.2 | nên khử |
| 200 | 38.1 ms | 0.605 ms | 12.6 | 19.4 | **bắt buộc** |
| 475 | 90.6 ms | 1.436 ms | 7.3 | 19.4 | **bắt buộc** |

Hình: `results/fig01_pipeline.png` (đường chéo tán sắc, định luật `SNR ∝ √t`,
hồ sơ xung, đường cong DM và hai cách đo DM) và `results/fig02_dm_fft.png`.

---

## 7. Giới hạn lý thuyết — đọc trước khi mơ

1. **Chảo 3.7 m chỉ có `A_eff ≈ 5.9 m²`** → `SEFD ≈ 70 kJy` ở `T_sys = 150 K`.
   Đây là con số quyết định tất cả (xem `02`).
2. **Beam 4°** ở 1.4 GHz: tốt cho việc trỏ (không cần chính xác), nhưng nghĩa là
   nền thiên hà + nguồn rộng đi vào chùm tia → `T_sys` thực tế cao hơn.
3. **Không có khử tán sắc kết hợp** → không thấy cấu trúc dưới ~1 ms ở 1.4 GHz.
4. **1 phân cực** → không đo RM/hình học từ trường.

→ Kết luận được lượng hoá ở `02` (ngân sách S/N) và `05` (kế hoạch + cổng quyết định).
