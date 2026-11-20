# 03 — Đo được gì từ một pulsar (vị trí, đặc điểm vật lý) với RTP-3.7

*Trả lời câu hỏi: "ngoài việc phát hiện, ta còn lấy được gì?"*
*Số liệu suy ra: `python code/psr_targets.py --derived`*

---

## 1. Bức tranh tổng quát

Từ **một** pulsar, tuỳ dữ liệu thu được, ta có thể lấy tới ~12 đại lượng. Chúng xếp
theo "giá trị khoa học / chi phí":

| #   | Đại lượng                               | Cho biết                                | Cần gì                     | RTP-3.7                             |
| --- | --------------------------------------- | --------------------------------------- | -------------------------- | ----------------------------------- |
| 1   | **P** (chu kỳ)                          | chu kỳ quay                             | fold + timing              | ✅ ngay                              |
| 2   | **W50, dạng hồ sơ**                     | hình học vùng phát xạ, độ cao phát xạ   | hồ sơ SNR ≥ 10             | ✅ ngay                              |
| 3   | **DM**                                  | mật độ electron tích phân → khoảng cách | A11b                       | ✅ ngay                              |
| 4   | **S, chỉ số phổ α**                     | vật lý phát xạ, phân loại               | đo ở 2 tần số (408 + 1400) | ✅ (nếu có FE 408)                   |
| 5   | **Ṗ** → `B`, tuổi, `Ė`                  | từ trường, lịch sử                      | timing ≥ 3–6 tháng         | ⚠ cần GPSDO                         |
| 6   | **Vị trí**                              | toạ độ, liên kết với SNR / cụm sao      | trỏ + timing astrometry    | ⚠ ±0.5° (beam), ≤ 1″ nếu timing dài |
| 7   | **Tán xạ `τ_sc`**                       | môi trường liên sao dọc tia nhìn        | đuôi hồ sơ xung            | ✅ nếu SNR cao                       |
| 8   | **Scintillation**                       | thang không gian/vận tốc của plasma     | chuỗi động phổ dài         | ❌ (cần S/N cao)                     |
| 9   | **Giant pulse / nulling / mode change** | vật lý magnetosphere                    | xung đơn, A3               | ⚠ rất khó                           |
| 10  | **RM, hình học từ trường (RVM)**        | cấu hình từ trường, độ cao phát xạ      | 2 phân cực                 | ❌ thiết bị                          |
| 11  | **Glitch, thị sai, quỹ đạo sao đôi**    | kiểm tra GR, khối lượng                 | timing nhiều năm           | ❌                                   |
| 12  | **Hấp thụ HI về phía pulsar**           | khí lạnh dọc tia nhìn                   | cần continuum mạnh         | ❌ với pulsar yếu                    |

---

## 2. Vị trí — làm được tới đâu?

Đây là chỗ dễ ảo tưởng nhất, nên nói rõ bằng số.

| Việc | Độ chính xác đạt được | Điều kiện |
|---|---|---|
| Xác nhận **đang trỏ đúng** mục tiêu | ±2° (nửa beam) | chỉ cần beam 4° + encoder |
| Đo **độ lệch trỏ** (pointing model) | ±0.2–0.5° | 5-point map trên Cas A / Mặt Trăng |
| Đo vị trí pulsar **bằng map chùm tia** | ±0.5° (≈ 1800″) | SNR ≥ 20, quét 5 điểm |
| Vị trí **từ timing** (TOA astrometry) | 0.1–1″ | 6–12 tháng TOA + GPSDO + barycentric |
| Vị trí một pulsar **mới** (blind survey) | ±1–2° rồi thu hẹp bằng timing | không thực tế với chảo 3.7 m |

**Kết luận**: chảo 3.7 m **không phải** dụng cụ đo vị trí. Vị trí lấy từ ATNF; việc ta
làm là **kiểm tra** và **hiệu chỉnh mô hình trỏ**. Muốn toạ độ chính xác, phải làm
timing dài hạn (giai đoạn 4).

---

## 3. P, Ṗ → từ trường, tuổi, công suất (bảng số thật)

```
B_s   = 3.2×10¹⁹ √(P·Ṗ)            [G]   (giả định lưỡng cực)
τ     = P/(2Ṗ)                      [yr]  (tuổi đặc trưng)
Ė     = 4π²I·Ṗ/P³,  I = 10³⁸ kg m²  [W]
d_DM  = DM/⟨n_e⟩,   ⟨n_e⟩ ≈ 0.03 cm⁻³ [pc] (chỉ bậc độ lớn)
```

| Pulsar | P (ms) | Ṗ | B (G) | Tuổi (yr) | Ė (W) | d_DM (kpc) | Loại |
|---|---|---|---|---|---|---|---|
| B0950+08 | 253 | 2.3e-16 | 2.4e11 | 1.7e7 | 5.6e25 | 0.1 | thường (già) |
| B1929+10 | 227 | 1.2e-15 | 5.2e11 | 3.1e6 | 3.9e26 | 0.1 | thường |
| B1133+16 | 1188 | 3.7e-15 | 2.1e12 | 5.1e6 | 8.8e24 | 0.2 | thường |
| B0329+54 | 715 | 2.0e-15 | 1.2e12 | 5.7e6 | 2.2e25 | 0.9 | thường |
| B0833−45 (Vela) | 89 | 1.3e-13 | 3.4e12 | **1.1e4** | 6.9e29 | 2.3 | **trẻ** |
| B0531+21 (Cua) | 33 | 4.2e-13 | 3.8e12 | **1.3e3** | **4.5e31** | 1.9 | **trẻ nhất** |
| J0437−4715 | 5.8 | 5.7e-20 | 5.8e8 | 1.6e9 | 1.2e27 | 0.1 | **MSP** (tái gia tốc) |
| B1641−45 | 455 | 1.0e-14 | 2.2e12 | 7.1e5 | 4.3e26 | 15.8 | thường |
| B1706−44 | 102 | 9.4e-14 | 3.1e12 | 1.7e4 | 3.5e29 | 2.5 | trẻ |
| B1937+21 | 1.6 | 1.1e-19 | 4.1e8 | 2.4e8 | 1.1e29 | 2.4 | **MSP** |

Đọc bảng này ra được ba câu chuyện vật lý:

1. **Pulsar trẻ** (Cua, Vela): `B ~ 10¹² G`, tuổi 10³–10⁴ năm, `Ė ~ 10³⁰ W` — nguồn
   năng lượng của tinh vân pulsar (Cua nebula sáng vì pulsar bơm `4.5e31 W`).
2. **Pulsar già** (B0950+08, B1133+16): tuổi 10⁶–10⁷ năm, `B` vẫn `10¹¹–10¹² G`.
3. **MSP** (J0437, B1937+21): `B` nhỏ 3–4 bậc (`10⁸–10⁹ G`) vì đã được **tái gia
   tốc** trong hệ sao đôi; tuổi đặc trưng **ảo** rất lớn (1.6e9 yr) — cảnh báo: đừng
   đọc tuổi MSP từ công thức `P/2Ṗ`.

**Đo `Ṗ` cần gì?** Không đo trực tiếp từ `P`, mà từ **fit TOA dài hạn**: phần pha
"dư" do `Ṗ` tích luỹ là `½·Ṗ·t²/P`. Với B0329+54 sau 6 tháng (`t = 1.55×10⁷ s`):
`½·2e-15·t² = 0.24 s` ≈ 0.34 chu kỳ — **rất lớn**, đo được với TOA ổn định cỡ chục
ms. Nghĩa là nút thắt **không phải độ nhạy** mà là **đồng hồ (GPSDO) + hiệu chỉnh
barycentric + template ổn định**. Đó là lý do `Ṗ` xếp vào giai đoạn 4, không phải vì
cần chảo to hơn.

---

## 4. DM và khoảng cách — chỗ hay sai

`d = DM/⟨n_e⟩`: **chỉ đúng bậc độ lớn**. So sánh với khoảng cách đo bằng thị sai VLBI:

| Pulsar | `d_DM` (0.03 cm⁻³) | `d` thật (VLBI) | Nhận xét |
|---|---|---|---|
| B0950+08 | 0.1 kpc | ~0.13 kpc | tốt |
| B0329+54 | 0.9 kpc | ~1.0 kpc | tốt |
| Cua | 1.9 kpc | ~2.0 kpc | tốt |
| **Vela** | **2.3 kpc** | **0.29 kpc** | **sai 8 lần** — vùng `n_e` rất thấp |

⇒ Quy tắc: **báo DM (đại lượng đo được) và chỉ báo khoảng cách kèm sai số ±50 %
hoặc kèm mô hình (NE2001/YMW16)**. Với Vela, mô hình vẫn sai vì vùng không gian
xung quanh nghèo plasma.

---

## 5. Hình dạng hồ sơ xung — nhiều thông tin hơn tưởng tượng

Từ một hồ sơ xung SNR ≥ 15 ta lấy được:

| Đặc trưng | Ý nghĩa vật lý | Cách đo |
|---|---|---|
| `W50`, `W10` | độ rộng, hình học chùm phát xạ | boxcar/Gauss fit |
| **đuôi hàm mũ** | tán xạ liên sao `τ_sc` → môi trường | fit `exp(−t/τ)` |
| số đỉnh phụ | interpulse, "cone/double cone" | đếm đỉnh sau làm trơn |
| độ bất đối xứng | hiệu ứng aberration–retardation → độ cao phát xạ | so sánh sườn lên/xuống |
| thay đổi `W` theo tần số | `W ∝ ν^-α_w` → vị trí phát xạ | đo ở 408 và 1400 MHz |
| biên độ theo tần số | chỉ số phổ `α` | đo `S` ở 2 dải |

**Đo được ngay với RTP-3.7** (sau khi có mục tiêu SNR ≥ 15): `W50`, đuôi tán xạ,
`α`. Đây là những đóng góp khoa học **thực tế** của một kính nhỏ.

---

## 6. Những thứ "gần như không thể" — nói thẳng

| Thứ | Vì sao không | Cần gì |
|---|---|---|
| Đo khối lượng sao neutron | cần timing pulsar đôi, µs, nhiều năm | chảo lớn + GPSDO + nhiều năm |
| Kiểm tra thuyết tương đối rộng | như trên | như trên |
| Bản đồ vị trí pulsar mới | beam 4° | mảng interferometer |
| Đo đường kính phát xạ | cần xung đơn µs | A3 + B ≥ 100 MHz |
| Hình học từ trường chi tiết | 2 phân cực | feed 2 pol + hiệu chuẩn |
| Phát hiện glitch | cần timing liên tục | GPSDO + 1 năm |

---

## 7. Metadata phải lưu cho mỗi quan sát (không có thì dữ liệu vô dụng)

```yaml
target: B0950+08
ra_deg: 148.28881, dec_deg: 7.92659     # J2000, từ ATNF
t_start_utc: 2026-11-19T13:22:05.123Z
t_total_s: 21600, nchan: 64, bw_mhz: 40, tsamp_us: 25
f_center_mhz: 1400.0
az_start_deg: ..., el_start_deg: ...     # từ encoder RTP-3.7
pointing_source: encoder | manual
tsys_k: 152 (đo bằng Y-factor)  |  sefd_jy: 71000
gain_db: 38.6, sample_counter_start: 0, dropped_samples: 0
dm_used: 2.970, period_used_s: 0.2530651
rfi_mask: [4, 5, 33]                     # kênh bị bỏ
notes: "mây thấp, RFI DVB-T mạnh lúc 21h"
```

Thiếu `t_start_utc` + `sample_counter` + `tsys` ⇒ **không thể cộng dồn nhiều đêm,
không thể công bố SNR**. Đây là lỗi phổ biến của các dự án nghiệp dư.

---

## 8. Giá trị thực tế lớn nhất của chương trình này

Xếp theo "chắc chắn làm được" (không phải theo độ hấp dẫn):

1. **Chuỗi thu + pipeline pulsar hoạt động và được kiểm chứng** (đã có: 16/16 test).
2. **Đo `T_sys`/SEFD/gain thật của kính** → mọi quan sát sau (kể cả HI) đều được
   hưởng lợi, vì hiện tại mọi thứ đang ở "a.u.".
3. **Phát hiện 1–2 pulsar sáng nhất** (B0950+08; có thể Vela) sau khi nâng băng thông
   → hồ sơ xung, SNR, DM độc lập, `α` nếu có 2 dải tần.
4. **Đo giới hạn trên (upper limits)** cho các pulsar không thấy — có giá trị nếu
   ghi rõ `T_sys`, `B`, `t`; là dữ liệu hiệu chuẩn cho cộng đồng nghiệp dư.
5. Bài học/kỹ năng: DSP tín hiệu yếu, RFI, hiệu chuẩn — chuyển trực tiếp sang HI.
