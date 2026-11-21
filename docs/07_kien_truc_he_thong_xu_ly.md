# 07 — Kiến trúc hệ thống xử lí (đặc tả đã chốt)

**Trạng thái: THIẾT KẾ ĐÃ CHỐT — CHƯA TRIỂN KHAI.** Tài liệu này là bản đặc tả
để triển khai dần theo các mốc M1–M5. Code hiện tại (baseline) **chưa** thay đổi.

Mục tiêu của lần nâng cấp:
1. Tách cấu hình trạm/kính khỏi code → dùng được cho kính và địa điểm khác.
2. Xử lí được file 4–18 GB trên máy 8 GB (đọc theo khối, ngân sách RAM rõ ràng).
3. Dò được tín hiệu **không biết trước** (DM rộng + dò chu kỳ mù + danh sách ứng viên).
4. Mọi kết luận đều có bằng chứng kiểm chứng được (injection–recovery, provenance).

---

## 0. Phạm vi

| Trong phạm vi | Ngoài phạm vi (ghi rõ để không kỳ vọng sai) |
|---|---|
| Xử lí offline, một mục tiêu, Stokes I | Phát hiện thời gian thực khi quay chảo |
| Transit / drift (chảo cố định) và tracking | Dò Ṗ, dò gia tốc quỹ đạo (hệ đôi) |
| `.fil` là định dạng lõi, xuất PSRFITS khi cần | Hiệu chỉnh phân cực, flux tuyệt đối |
| 1 chùm tia, 1 kính | Multi-beam, interferometry |
| Kết luận mức "ứng viên" | Tuyên bố "phát hiện pulsar mới" (cần đài lớn xác nhận) |

---

## 1. Năm nguyên tắc

1. **Một hợp đồng dữ liệu, nhiều lớp dùng chung** — DSP thuần hàm, không I/O;
   vào/ra qua JSON có `schema_version`.
2. **Không phụ thuộc trạm/kính** — lat/lon, D, η, T_sys, băng đều từ *hồ sơ*.
3. **Không bịa (zero-hallucination)** — bước nào bỏ qua thì ghi rõ lý do; không có
   mốc thì không vẽ đường tham chiếu, không so sánh.
4. **Tái lập được** — mỗi kết quả kèm `input_sha256`, phiên bản code, hash hồ sơ,
   tham số, và số hạt giống ngẫu nhiên.
5. **Chạy được trên máy 8 GB** — đọc theo khối, giảm độ phân giải 2 tầng,
   `np.memmap`; không nạp cả file 4–18 GB vào RAM.

---

## 2. Kiến trúc 6 tầng

```
      ┌──────────────────────────────────────────────────────────┐
 L6   │ gui_app (Tk)  — form → gọi CLI → hiển thị JSON/ảnh        │  KHÔNG DSP
      └───────────────────────────┬──────────────────────────────┘
      ┌───────────────────────────▼──────────────────────────────┐
 L5   │ pulsarobs  plan|record|analyze|stack|verify|site          │  điều phối
      └───────────────────────────┬──────────────────────────────┘
      ┌───────────────────────────▼──────────────────────────────┐
 L4   │ psr_products — report.json / report.txt / hình / provenance│  sản phẩm
      └───────────────────────────┬──────────────────────────────┘
      ┌───────────────────────────▼──────────────────────────────┐
 L3   │ psr_dm · psr_pulse · psr_period · psr_veto                │  dò tìm
      └───────────────────────────┬──────────────────────────────┘
      ┌───────────────────────────▼──────────────────────────────┐
 L2   │ psr_core — dedisperse, fold, FFT, match filter, SNR       │  DSP thuần
      └───────────────────────────┬──────────────────────────────┘
      ┌───────────────────────────▼──────────────────────────────┐
 L1   │ psr_fil · psr_fits · psr_iq — đọc/ghi WHOLE → chuẩn hoá    │  I/O
      └───────────────────────────┬──────────────────────────────┘
      ┌───────────────────────────▼──────────────────────────────┐
 L0   │ psr_site (hồ sơ) · psr_constants (hằng số chuẩn)          │  cấu hình
      └──────────────────────────────────────────────────────────┘
```

| Tầng | Module | Trách nhiệm | Cấm làm |
|---|---|---|---|
| L0 | `psr_site.py` (mới), `psr_constants.py` (mới) | Profile trạm/kính/băng; hằng số vật lí có đơn vị | tính toán, I/O dữ liệu |
| L1 | `psr_fil.py`, `psr_fits.py`, `psr_iq.py` | Đọc/ghi, chuẩn hoá `Header` + `DynamicSpectrum`; **tách đoạn theo gap** | DSP |
| L2 | `psr_core.py` | dedisperse, fold, FFT+cộng hài, lọc khớp, RFI, SNR | đọc file, vẽ |
| L3 | `psr_dm.py`, `psr_pulse.py`, `psr_period.py`, `psr_veto.py` (mới) | kế hoạch DM 2 tầng, dò xung đơn, dò chu kỳ, veto | ghi sản phẩm |
| L4 | `psr_products.py` (mới) | report + hình + provenance + `export-pac` | DSP |
| L5 | `pulsarobs.py` (mới) | CLI, in JSON | logic khoa học |
| L6 | `gui_app.py` | form → CLI → hiển thị | DSP |

`psr_detect.py` giữ lại làm **wrapper tương thích** (API cũ `detect()` → gọi L3+L4),
để test và GUI hiện tại không vỡ trong lúc chuyển đổi.

---

## 3. Hợp đồng dữ liệu

### 3.1 `profile.json`

```json
{
  "schema_version": 1,
  "id": "poam-rtp37-hcmc",
  "site": {"name": "TP.HCM", "lat_deg": 10.7769, "lon_deg": 106.7009,
           "elev_m": 10, "tz_offset_h": 7},
  "telescope": {"name": "POAM RTP-3.7", "diameter_m": 3.7, "efficiency": 0.55,
                "mount": "fixed", "hpbw_mode": "auto"},
  "receiver": {"bands": [
    {"id": "423", "fc_mhz": 423, "bw_mhz": 20, "tsys_k": 200,
     "note": "cần BPF 380–450 MHz"},
    {"id": "lband", "fc_mhz": 1420, "bw_mhz": 2.4, "tsys_k": 150}]},
  "backend": {"type": "rtlsdr", "max_bw_mhz": 2.4, "bits": 8},
  "rfi": {"notch_mhz": [[88, 108]], "notes": "FM rất mạnh; CW bộ đàm 400–470"}
}
```
`hpbw_mode: "auto"` → HPBW tính từ D và f; `"manual"` → dùng `hpbw_deg` nhập tay.
Mọi hằng số suy ra (HPBW, G, SEFD) **không** lưu trong profile, luôn tính lại.

### 3.2 `session.json` (1 phiên quan sát)

```json
{
  "schema_version": 1,
  "profile_id": "poam-rtp37-hcmc",
  "target": {"name": "J1836-2105", "ra_deg": 279.1, "dec_deg": -21.1,
             "custom": true},
  "band": {"id": "423", "fc_mhz": 423, "bw_mhz": 20},
  "mode": "fixed",                       // fixed | track
  "source_mode": "auto",                 // auto | mock | real
  "requested": {"hours": 4.5, "nchan": 256, "tsamp_us": 256},
  "t0_utc": "2027-02-14T13:02:11Z", "t0_mjd": 61055.543183,
  "ntp_offset_ms": 12.4,
  "segments": [
    {"i": 0, "first_row": 0, "rows": 812345, "t_start_s": 0.0},
    {"i": 1, "first_row": 812345, "rows": 640211, "t_start_s": 208.06}
  ],
  "gaps": [{"after_row": 812345, "missing_samples": 620, "t_rel_s": 208.06,
            "reason": "usb"}],
  "bandpass_blocks": [{"t_start_s": 0.0, "t_end_s": 600.0, "scale": 1.0,
                       "channels_flagged": [17, 208], "adc_clip_frac": 0.0002}],
  "integrity": {"sha256": "...", "bytes": 4061000000, "roundtrip_ok": true}
}
```

**Bắt buộc:** `segments[].first_row` **và** `gaps[].after_row` (theo **chỉ số mẫu**,
không chỉ theo giây) — xem §6.2. Nếu thiếu, pha tuyệt đối không tái lập được.

### 3.3 `report.json` (schema v3)

```json
{
  "schema_version": 3,
  "status": "ok|too_short|unreadable|invalid|rfi_zero_dm|partial",
  "input": {"file": "...", "nchans": 256, "tsamp_s": 0.000256, "t_s": 16200,
            "band_mhz": [413, 433], "segments": 2, "data_loss_pct": 0.4},
  "stages": {
    "calibrate": {"bandpass_blocks": 27, "channels_flagged": 3,
                  "adc_clip_frac": 0.0002, "status": "ok"},
    "dm_search": {"dm_max": 1000, "trials": 1873, "best": 56.71,
                  "resolution": 0.25, "status": "ok"},
    "pulse":     {"n": 3, "best_snr": 108.3, "status": "ok"},
    "period":    {"searched": true, "range_s": [0.0015, 10.0], "trials": 2013488,
                  "top": [{"p_s": 0.253065, "snr": 12.4, "harm": 2}],
                  "status": "ok"},
    "veto":      {"zero_dm": {"ok": true, "ratio": 28.2},
                  "subband_dm": {"ok": true, "dm": 56.71, "err": 0.57},
                  "off_source": {"ok": null, "reason": "không có dữ liệu ngoài nguồn"}}
  },
  "candidates": [
    {"id": "C1", "kind": "periodic", "dm": 56.71, "p_s": 0.253065, "snr": 12.4,
     "significance_corrected": 7.9, "class": "nghi vấn",
     "needs": ["lặp lại ≥2 phiên"], "figures": ["fig2_detection.png"]}
  ],
  "checks": [{"name": "DM vs tham chiếu", "ok": true, "detail": "..."}],
  "figure_check": [],
  "provenance": {"code_version": "1.2.0", "profile_sha256": "...",
                 "params_sha256": "...", "input_sha256": "...",
                 "rng_seed": 0, "runtime_s": 512.3}
}
```

Quy tắc: `report.json` chỉ chứa **số đã tính**; `report.txt` sinh từ nó; biểu đồ
đọc từ nó. Không có giá trị nào xuất hiện ở hai nơi do hai nguồn khác nhau.

---

## 4. Luồng xử lý (mỗi bước có `status` riêng)

1. **Đọc** (L1): header → chuẩn hoá; tách `segments` theo gap; tính `data_loss_pct`.
2. **Hiệu chuẩn** (L1/L2): bandpass trượt 600 s (median+MAD), cờ kênh
   (mean/MAD + spectral kurtosis + bursty + RFI tuần hoàn), cờ bão hoà ADC.
3. **Trọng số theo chế độ**: `fixed` → cửa sổ transit Gauss; `track` → đều 1.0.
4. **Dò DM 2 tầng**: thô trên chuỗi giảm độ phân giải (4 ms, ≤32 dải con),
   mịn ±(3 bước) quanh top-K ở độ phân giải gốc.
5. **Dò xung đơn** trên chuỗi đã khử tán sắc (boxcar đa độ rộng, gom cụm).
6. **Dò chu kỳ** (FFT + cộng hài k=1,2,4,8) trên từng đoạn, cộng phổ không kết hợp;
   fold lại bằng thời gian tuyệt đối (đã hiệu chỉnh barycentric nếu T > 600 s).
7. **Veto**: zero-DM, bursty, DM dải con, đối chứng nền xáo trộn, off-source (nếu có),
   lặp lại giữa các đêm (nếu có).
8. **Gom cụm ứng viên** trong không gian (DM, P, t) — một tín hiệu chỉ ra một ứng viên.
9. **Xếp hạng**: SNR + significance đã trừ số lần thử + nhất quán DM.
10. **Sản phẩm** (L4): report.json/txt, hình, (tuỳ chọn) chuỗi đã khử tán sắc để
    cộng dồn đêm sau, (tuỳ chọn) `export-pac`.

---

## 5. Hằng số & công thức chuẩn (`psr_constants.py`)

| Hằng số | Giá trị | Đơn vị |
|---|---|---|
| `K_DM` | 4.148808×10³ | s·MHz²·pc⁻¹·cm³ |
| `C_M_S` | 2.99792458×10⁸ | m/s |
| `K_B` | 1.380649×10⁻²³ | J/K |
| `AU_M` | 1.495978707×10¹¹ | m |
| `MJD_2000` | 51544.5 | ngày (J2000) |

Các công thức **bắt buộc dùng chung** (không viết lại trong module khác):

- Nhòe nội kênh tại `fc` (MHz), `Δf` (MHz), DM:
  `t_smear(ms) = 8.2976e6 · Δf · DM / fc³`
  → kiểm tra: 423 MHz, Δf = 0.3125 (20 MHz/64 kênh), DM 50 → **1.71 ms**.
- Trễ toàn băng/tại 1 đơn vị DM: `Δt = K_DM · DM · |1/f_low² − 1/f_high²|`
  → 423 MHz, 20 MHz, DM 1000 → **2.19 s**; DM 3000 → **6.6 s**.
- `check_channelization(fc, bw, nchan, dm_expected, w50_ms)` → cảnh báo nếu
  `t_smear > 0.5·W50`. Kênh tối thiểu gợi ý: `nchan ≥ 2·bw/Δf_max`.
- HPBW (deg) = `1.22 · (C/f) / D · 180/π` → 3.7 m @423 MHz = **13.4°**.
- G (mK/Jy) = `1e-26 · η·A / (2·K_B)` → 3.7 m, η=0.55 = **2.14 mK/Jy**.
- SEFD (Jy) = `2·K_B·T_sys / (η·A)` → T_sys 150 K = **70 kJy**.
- Barycentric: sai số **phải ≤ P/4**. Với P = 1.5 ms → cần ≤ **0.37 ms**;
  mô hình Rømer tuyến tính (~40 dòng NumPy, không cần astropy) đạt ~0.2 ms.
  **Chỉ áp dụng khi fold/cộng đêm**; dò FFT làm trong **thời gian topocentric**
  (P tìm được là P topocentric, phải ghi rõ trong report).

---

## 6. Hai cơ chế đặc biệt (đã chốt)

### 6.1 Bandpass trượt 600 s

- Mỗi khối 600 s: `median` + `MAD` **theo từng kênh** (không dùng mean/std).
- Lưu **cả hai**: `scale[t]` (mức công suất của khối) **và** `channels_flagged[t]`
  (cờ kênh có thể đổi giữa các khối — không lưu thì RFI xuất hiện muộn sẽ lọt).
- **Hệ quả có chủ đích:** chuẩn hoá từng khối làm phẳng biến thiên công suất tổng.
  Muốn quan sát continuum thì dùng `scale[t]` — **đừng** bỏ bước chuẩn hoá.
- Kênh bị cờ > 30 % số khối → cắt cho toàn phiên (ghi vào report).
- Bão hoà ADC: lưu `adc_clip_frac` mỗi khối; cảnh báo nếu > 0.1 %.

### 6.2 Gap → tách đoạn (không zero-pad)

- Không đệm 0: đệm 0 làm đổi thống kê nhiễu và tạo vạch phổ giả.
- Mỗi đoạn liên tục có `first_row`, `rows`, `t_start_s` **chính xác theo chỉ số mẫu**
  (trình ghi phải log `after_row` + `missing_samples`; log theo giây là không đủ).
- **Fold**: pha tính từ thời gian tuyệt đối so với `t0`:
  `φ(t) = ((t − t0)/P) mod 1` → nối pha đúng qua mọi khoảng trống.
- **FFT**: chạy trên từng đoạn ≥ 60 s, rồi **cộng phổ công suất không kết hợp**
  (chuẩn hoá về cùng lưới tần số, trọng số theo độ dài đoạn). Không FFT trên
  chuỗi đã ghép.
- **Khử tán sắc**: trong nội bộ từng đoạn (nếu gap < Δt_DM thì mất một phần xung —
  chấp nhận và ghi vào report).
- Report ghi: `segments: N`, `data_loss_pct`, và cảnh báo nếu một đoạn < 60 s.

---

## 6c. Tầng nhận dữ liệu & tự fallback (`ingest_guard.py`)

Đây là **cổng vào duy nhất** của mọi dữ liệu (file hay stream). Nó chạy **trước** mọi
thuật toán thiên văn và quyết định: dữ liệu ở trạng thái nào, có tin được không, và
phải xử lý tiếp thế nào. Không có tầng này thì mọi kết luận phía sau đều vô nghĩa.

### 6c.1 Lớp A — Hợp đồng metadata (bắt buộc khai báo)

Mỗi phiên/file phải có (`session.json` hoặc header):

```json
{"stage": "RAW_IQ | CHANNELIZED_POWER | DEDISPERSED_TS",
 "hardware_id": "rtlsdr_v5 | N6002 | ...", "adc_bits": 8,
 "sample_rate_hz": 2400000, "center_freq_hz": 1420000000,
 "calibrated": false,
 "time_sync": "GPS_PPS | NTP | LOCAL_CLOCK",
 "nchan": 256, "tsamp_s": 0.000256, "t0_mjd": 61055.543,
 "telemetry": {"t_lna_c": 31.2, "t_rack_c": 27.8, "adc_clip_frac": 0.0002,
               "tsys_k": 97.5, "y_factor_ts": 2.08}}
```

Quy tắc: **thiếu trường nào thì Lớp B phải suy ra trường đó và ghi lại `"inferred": true`**.
Không được im lặng dùng mặc định.

### 6c.2 Lớp B — Nhận dạng mù từ chính mẫu dữ liệu (0,1–1 s đầu)

| Dấu hiệu toán học đo được | Kết luận | Hành động tự động |
|---|---|---|
| dtype phức (`complex64`/cặp I,Q), có cả giá trị âm & dương | **Raw I/Q** chưa FFT | Bật nhánh DSP: cửa sổ Hann/PFB → FFT → \|X\|² ; ghi `stage=RAW_IQ` |
| Số thực **P ≥ 0**, dạng ma trận (time × freq) | Back-end đã FFT + tích phân | **Bỏ FFT**; đọc `Δt` để định tuyến: **≤ 1 ms → nhánh pulsar**, **> 10 ms → HI/continuum**; 1–10 ms → cảnh báo "quá chậm cho pulsar, quá nhanh cho HI" |
| Đường bao phổ **cong vòm**, hai rìa tụt **> 3 dB** trong 15 % băng | Bandpass **chưa** làm phẳng | Bật flatten (chia trung vị trượt theo thời gian) + `edge_zap` 10 % hai mép |
| Phổ **phẳng ~1.0 (0 dB)** toàn dải | Đã hiệu chuẩn ở tầng trước | **Tắt** flatten (chia 2 lần sẽ méo nhiễu nền); ghi `calibrated=true` |
| Đỉnh nhọn đúng kênh **N/2**, cao > 3× trung vị | Rò **DC offset** (Zero-IF) | DC notch: thay kênh N/2 bằng trung bình 2 kênh lân cận; cảnh báo nếu > 10× |
| **Bộ đếm mẫu nhảy bước** hoặc thiếu gói USB | Mất đồng bộ / nghẽn USB | Chuyển từ fold liên tục sang **cộng dồn từng đoạn ngắn + cross-correlation** (không lệch pha); ghi `segments` |
| `time_sync = LOCAL_CLOCK` | Thạch anh trôi ~1–2 ppm | **Mở rộng dải tìm chu kỳ** (± vài ppm quanh P danh định) thay vì khoá cứng P từ ATNF |

Ngưỡng phải **đo được**, không phải cảm tính:
`r_edge = median(15 % mép)/median(giữa băng)`; `dc_ratio = P[N/2]/median(P)`;
`neg_frac = số mẫu < 0 / tổng`; `is_complex = np.iscomplexobj(x)`.

### 6c.3 Gatekeeper — 4 nhóm thông số vật lý

**① Bão hoà ADC (đo trên dữ liệu I/Q thô; với dữ liệu đã FFT thì lấy từ telemetry)**

| Tỷ lệ mẫu chạm ngưỡng (`|x| ≥ 126` với 8-bit) | Hành động |
|---|---|
| < 0,01 % | OK |
| 0,01–0,5 % | **WARN**: chuyển thống kê từ mean/std sang **median/MAD** cho khối đó |
| > 0,5 % | **ABORT khối** + log "giảm gain / kiểm tra BPF"; gắn tag `SATURATED` |

**② Nhiễu nhiệt & RFI**

- **Radiometer**: `σ_P/μ_P = 1/√(Δf·τ)`. Lệch > **20 %** so với lý thuyết → nền bất ổn
  (trôi gain hoặc nhiễu biến thiên) → tag `GAIN_DRIFT`; nhưng **so với kênh đối chứng**
  để tránh nhầm với nguồn continuum thật.
- **Spectral Kurtosis** (Nita estimator) cho từng kênh mỗi 1–5 s:
  `SK = (M+1)/(M−1)·[M·Σp²/(Σp)² − 1]`, cần **M ≥ 1000 mẫu/kênh/khối** mới có nghĩa.
  Ngoài khoảng `1 ± 3σ_SK` (`σ_SK ≈ √(4/M)`) → cờ **RFI mask**, loại kênh khỏi cộng dồn.

**③ Nhiệt độ & hiệu chuẩn T_sys**

- Đọc `T_LNA`, `T_rack` mỗi **10 s** (I2C/serial) → ghi vào `telemetry`.
- Y-factor khi có noise source: `Y = P_ON/P_OFF ⇒ T_sys = T_cal/(Y−1)`, đầu phiên và
  mỗi **30–60 phút**. **Không có noise source** → Y-factor bằng Mặt Trời/Mặt Trăng/Cas A
  (sai số 20–30 %, ghi rõ `tsys_method` trong report).
- `T_sys > 1.5 × T_sys_chuẩn` → kiểm tra góc cách Mặt Trời và **elevation < 15°**
  (nhiễu đất tràn mép chảo) → tag `DATA_QUALITY=DEGRADED`.
- `ΔT_LNA > 2 °C` trong phiên → **rút cửa sổ bandpass từ 600 s xuống 180 s** để bám trôi.

**④ Gắn nhãn (tagging)** — mỗi khối dữ liệu mang: `VALID`, `RFI_HEAVY`, `GAIN_DRIFT`,
`SATURATED`. Nhãn vào `report.json → input.tags[]` và hiển thị trên hình.

### 6c.4 Máy trạng thái (chạy trước mọi thuật toán)

```
1 Inspect   : header + 0.1–1 s mẫu → stage, Δf, Δt, mức đã xử lý
2 Sanitize  : bật/tắt FFT, DC notch, flatten, edge_zap, chế độ fold
3 Gatekeep  : ADC clip, radiometer, SK, nhiệt độ, T_sys
4 Tagging   : VALID / RFI_HEAVY / GAIN_DRIFT / SATURATED → xuống L3
```

Mọi quyết định ở bước 1–2 phải **ghi lại** (`report.json → input.guard`): đã bật gì,
tắt gì, suy ra gì, vì sao. Đây là điều kiện để kết quả tái lập được.

## 7. Ngân sách bộ nhớ / thời gian (máy 8 GB)

Phiên 4.5 h, tsamp 256 µs.

| Cấu hình | File | Dò DM thô (4 ms, 32 dải con) | Dò DM mịn | FFT chu kỳ | Tổng RAM | Thời gian |
|---|---|---|---|---|---|---|
| 64 kênh / 2.4 MHz | ~1.0 GB | ~60 MB × 27 khối | ~500 MB (float16) | ~200 MB | **< 1 GB** | 3–5 phút |
| 256 kênh / 20 MHz | ~4.0 GB | ~240 MB × khối | ~1.2 GB (memmap) | ~400 MB | **< 2 GB** | 10–15 phút |
| 256 kênh / 56 MHz | ~11 GB | như trên | memmap | memmap | **< 2 GB** | 20–30 phút |

Cơ chế: đọc khối 60 s + chồng lấn = 10 s (> trễ DM 3000 @20 MHz = 6.6 s);
giảm độ phân giải 2 tầng; `np.memmap` cho mảng lớn; float16 cho chuỗi trung gian.

---

## 8. Chế độ quan sát

Gộp `transit` và `drift` thành **một** chế độ `fixed` (vật lí giống nhau: trời trôi
qua búp sóng tĩnh), khác nhau chỉ ở **ý định** — phản ánh bằng `pointing_log`:

| Mode | Metadata bắt buộc | Xử lý |
|---|---|---|
| `fixed` (transit / drift scan) | RA/Dec trỏ, `t0`, (tuỳ chọn) log hướng trỏ theo thời gian | trọng số Gauss theo cửa sổ transit; nếu có `pointing_log` thì dùng để quy ứng viên về toạ độ |
| `track` | RA/Dec đích + sai lệch bám | trọng số đều 1.0; T_eff = toàn bộ thời lượng |

Thiếu `pointing_log` ở chế độ `fixed` → ứng viên vẫn báo nhưng `class` bị hạ xuống
`nghi vấn` kèm lý do "không xác định được toạ độ".

---

## 9. Veto, xếp hạng, phân loại

| Veto | Tiêu chí | Thiếu dữ liệu thì |
|---|---|---|
| zero-DM | SNR(DM=0) ≥ SNR_peak/1.15 | không veto (ghi "chưa kiểm") |
| DM dải con | lệch ≤ max(1.5, 6 % DM) | không veto |
| Kênh bursty | P99.9/median > 3 | cắt kênh, ghi số kênh cắt |
| RFI tuần hoàn | đỉnh hẹp lặp lại trong phổ từng kênh | cảnh báo |
| Nền xáo trộn | SNR nền < 12 | không veto |
| Off-source | SNR_off đủ thấp | "chưa kiểm" (không phải đạt) |
| Lặp lại đêm khác | cùng DM ± tolerance, cùng P ± 1 % | `nghi vấn`, không phải `xác nhận` |

Ngưỡng (đã tính trials): **nghi vấn ≥ 6.5σ**, **xác nhận ≥ 8.5σ** hoặc
**6.5σ lặp lại ở ≥ 2 phiên độc lập**. Kiểm tra: với ~2×10⁶ phép thử FFT,
6.5σ cho FPR ~10⁻³/phiên; 5σ sẽ cho ~0.6 báo động giả/phiên → **không dùng 5σ**.

Ba mức: `xác nhận` · `nghi vấn` · `loại` (kèm lý do). Không bao giờ in "pulsar mới".

---

## 10. Sản phẩm & lưu trữ

```
results/<stem>/
├── report.json          (schema v3, số đã tính)
├── report.txt           (bản đọc được, sinh từ JSON)
├── fig1_overview.png    waterfall gốc + đã khử tán sắc
├── fig2_detection.png   4 panel + figure_check
├── fig3_period.png      (M3) phổ công suất + hồ sơ fold
├── candidates/          (M3) một thư mục/ứng viên: hình + JSON
└── replay/              (tuỳ chọn) chuỗi đã khử tán sắc để cộng dồn đêm sau
```

- `--export-pac`: zip gồm hình chẩn đoán, đoạn `.fil` cắt gọn quanh ứng viên
  (vài chục MB), `candidate_summary.json` (J2000, MJD, P_topo, DM, provenance),
  **kèm cảnh báo** "chưa hiệu chỉnh phân cực / flux tuyệt đối".
- Lưu trữ: 4 GB/đêm → ~1.4 TB/năm. Chính sách: giữ sản phẩm + `replay` (nén),
  xoá raw sau N ngày (mặc định 30) trừ khi được đánh dấu `keep`; kèm `sha256` +
  `manifest.json` để biết file nào đã xử lý.

---

## 11. Các mốc triển khai

| Mốc | Nội dung | Tiêu chí XONG (cổng) |
|---|---|---|
| **M0** (đã có) | Baseline hiện tại | selftest 23/23, gui 48/48, nghiệm thu 67/67 |
| **M1** | `psr_site` + `psr_constants` + refactor hằng số + **khung `ingest_guard` (§6c)** | **Không đổi hành vi**: M0 vẫn xanh; profile mặc định cho lại đúng 13.4° / 2.14 mK·Jy⁻¹ / SEFD 70 kJy |
| **M2** | Dò DM 2 tầng + đọc theo khối + **Lớp B/gatekeeper đầy đủ** | File 4 h (4 GB) xử lí với **RSS < 2 GB**, **< 20 phút**; kết quả trên B0329+54 và Cua lệch < 1 bước DM so với baseline |
| **M2.5** | **Injection–recovery** (cổng bắt buộc) | `capability_matrix.md` tự sinh; completeness ≥ 80 % ở SNR ≥ 10 cho DM ≤ 500; FPR ≤ 0.5 ứng viên/giờ; chạy trong bộ test |
| **M3** | Dò chu kỳ mù + danh sách ứng viên + gom cụm | Tìm lại **P của B0950+08 và B0329+54 khi KHÔNG truyền P**; completeness/FPR tốt hơn baseline M2.5 (đo bằng chính harness đó) |
| **M4** | `fixed`/`track` + pointing log + trọng số | T_eff & trọng số đúng; test nam bán cầu (lat −33°) không giả định bắc bán cầu |
| **M5** | `pulsarobs` CLI + schema v3 + provenance + `export-pac` | Mọi lệnh trả JSON hợp lệ (validate schema); nghiệm thu mở rộng xanh |

Thứ tự **không được đảo**: M2.5 là thước đo của M3.

---

## 12. Tham số mặc định (đã chốt)

| Tham số | Giá trị | Ghi chú |
|---|---|---|
| `dm_max` | **1000** (`--dm-max 3000` khi cần) | Pulsar sáng đều có DM < 800 |
| `dm_step` | thích ứng, sàn 0.1, `≈0.2·W50/Δt_per_dm` | Giảm ~2× số trial |
| Dải chu kỳ | **1.5 ms – 10 s** | Dưới 1.5 ms: chi phí FFT tăng 4× mà vô ích với 2.4 MHz |
| Dò Ṗ | **Không** | Có cảnh báo "nghi hệ đôi" khi SNR fold thấp bất thường |
| Phân cực | Stokes I | |
| Định dạng | `.fil` lõi; PSRFITS khi xuất | |
| Off-source | Tuỳ chọn; mặc định dùng rìa cửa sổ transit làm nền | |
| Ngưỡng | 6.5σ nghi vấn / 8.5σ hoặc 6.5σ×2 phiên | |
| Kênh ↔ BW | 2.4 MHz → 64 kênh; 20 MHz → **256 kênh** | Kèm `check_channelization` |
| Bandpass | trượt **600 s**, median+MAD | §6.1 |
| Barycentric | bật khi T > 600 s, sai số ≤ P/4 | §5 |
| Gap | tách đoạn, không zero-pad | §6.2 |
| Cộng dồn đêm | thủ công `pulsarobs stack` | Không tự động (RFI khác nhau từng đêm) |

---

## 13. Bốn điểm đã chỉnh so với bản nháp (ghi để không tái diễn)

1. **Hằng số tán sắc**: bản nháp ghi `4.15×10⁶` → đúng là **4.148808×10³**
   (sai 1000 lần sẽ làm hỏng toàn bộ kế hoạch DM).
2. **Log gap**: phải theo **chỉ số mẫu** (`after_row`, `missing_samples`), không chỉ
   theo giây — nếu không, pha tuyệt đối khi fold/cộng đêm không tái lập được.
3. **Sai số barycentric**: "<10 ms là đủ" **chỉ đúng cho P > 40 ms**; yêu cầu đúng là
   **≤ P/4** (P = 1.5 ms → ≤ 0.37 ms). Và FFT search chạy ở **topocentric**.
4. **Bandpass trượt**: phải lưu **cả** `scale[t]` **và** `channels_flagged[t]`;
   chỉ lưu `scale` thì RFI xuất hiện giữa phiên sẽ lọt qua.

Ngoài ra, con số "nhòe nội kênh 2 ms" trong bản nháp là của cấu hình **20 MHz/64 kênh**;
với **2.4 MHz/64 kênh** chỉ là **0.21 ms** — không được trộn hai cấu hình khi lập luận.

---

## 14. Việc KHÔNG làm (và lý do)

- **Phát hiện thời gian thực khi quay chảo**: với D = 3.7 m, fold cần 30 phút–vài giờ
  mỗi điểm; quét cả bầu trời là 300+ giờ. Chỉ hữu ích cho giant pulse.
- **Dò Ṗ / gia tốc quỹ đạo**: tăng 10–50× khối lượng tính, tăng mạnh báo động giả.
- **Tự động cộng dồn nhiều đêm**: một đêm nhiễu nặng sẽ phá 4 đêm sạch.
- **Tự kết luận "pulsar mới"**: ngoài khả năng xác nhận của kính này.

---

## 15. Rủi ro kỹ thuật & giảm thiểu

| Rủi ro | Giảm thiểu |
|---|---|
| RFI TP.HCM làm ngập ứng viên | Veto 6 lớp + injection-recovery đo FPR thật trên nền RFI thật |
| RTL-SDR 8-bit bão hoà do CW mạnh | Cảnh báo `adc_clip_frac`, khuyến nghị gain/BPF, ghi vào report |
| Mất mẫu USB trong đêm dài | Tách đoạn + log chỉ số mẫu + `data_loss_pct`; chế độ `real` báo lỗi thay vì giả lập |
| Trôi gain theo nhiệt độ | Bandpass trượt 600 s |
| Không có toạ độ (mục tiêu vô danh) | Ứng viên bị hạ xuống `nghi vấn` + yêu cầu `pointing_log` |
| Bộ nhớ vượt 8 GB | Đọc khối + 2 tầng độ phân giải + memmap (ngân sách §7) |
