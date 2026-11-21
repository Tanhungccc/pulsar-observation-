# 06 — Phần cứng tối giản, bù trừ bằng phần mềm & ghi tự động

*Tài liệu này trả lời 3 yêu cầu: (1) tối giản phần cứng, bù bằng phần mềm;
(2) dự đoán chuỗi linh kiện + tự fallback; (3) ghi dữ liệu 4–5 giờ không cần
canh chừng. Code đi kèm: `psr_hw.py`, `psr_swcomp.py`, `record_unattended.py`.*

---

## 1. Nguyên tắc: phần cứng giữ tối thiểu, phần mềm gánh phần còn lại

```
BẮT BUỘC (vật lý):   [feed] → [LNA] → [SDR] → PC
CÓ THỂ TỐI GIẢN:     BPF, GPSDO, motor, bộ hiệu chuẩn, LNA dự phòng...
KHÔNG BÙ ĐƯỢC:       diện tích chảo · độ ồn LNA · băng thông · bão hoà ADC · phân cực
```

Ba giới hạn cuối là **định luật radiometer** — `SNR ∝ A_eff·√B/T_sys` — phần mềm
chỉ có thể khai thác hiệu suất, không thể thay đổi hệ số. Mọi thứ khác đều bù được.

### 1.1 Ma trận bù trừ (registry đầy đủ trong `psr_swcomp.COMPENSATIONS`)

| Thiếu phần cứng | Phần mềm bù thế nào | Module | Thiệt hại còn lại |
|---|---|---|---|
| **BPF** (lọc dải) | masking kênh + zero-DM phân biệt phổ phẳng/tập trung + cắt biên dải | `psr_core.zero_dm_excise` | ADC vẫn có thể bão hoà nếu RFI quá mạnh → **khuyến nghị vẫn mua BPF rẻ** |
| **GPSDO** | đo ppm từ chu kỳ pulsar catalogue → hiệu chỉnh P cho đêm sau | `psr_swcomp.measure_ppm` | timing nhiều tháng vẫn yếu |
| **Motor + encoder** | chế độ transit + trọng số chùm Gauss + UTC chính xác | `psr_swcomp.transit_weights` | mất ~45% thời gian treo (nhưng 0 phút canh chừng!) |
| **LNA ngoài hỏng** | gain nội SDR + cộng dồn nhiều đêm | `psr_swcomp.stack_profiles` | T_sys ×8 — **không cứu được**, thay LNA |
| **Nguồn hiệu chuẩn** | Y-factor tự động bằng Cas A / Mặt Trăng | `psr_swcomp.y_factor_tsys` | sai số SEFD ±10–15% |
| **Mô hình địa tâm** | hiệu chỉnh barycentric bằng astropy | `psr_swcomp.barycentric_delay_s` | thiếu astropy thì bỏ qua cho phiên < 1 h |
| **Không có SDR tại chỗ** | chế độ replay mô phỏng để test toàn chuỗi | `record_unattended.ReplaySource` | không có dữ liệu thật |

### 1.2 Cấu hình tối thiểu cụ thể (băng 423 MHz — xem `docs/02` §4.3)

| Bậc | Linh kiện | Giá tham khảo | 2.5 h → SNR (B0950+08) |
|---|---|---|---|
| **M0** | dipole tự chế + SPF5189Z + RTL-SDR (đã có) | < 1 tr | ~2.5 (8 đêm → 7) |
| **M1** | M0 + **BPF 380–450 MHz** (chống bão hoà ADC) | +1–2 tr | ~2.5 (nhưng sạch RFI) |
| **M2** | M1 + SDR 10–20 MHz | +5–8 tr | **7–10 → 1–2 đêm** |

> Kết luận trung thực: **M0/M1 + nhiều đêm** là đường "0 đồng" khả thi nhưng dài;
> **M2 là bước nhảy duy nhất đáng tiền** (băng thông không phần mềm nào thay được).

---

## 2. Tự phát hiện & fallback chuỗi linh kiện (`psr_hw.py`)

`detect_chain(band, have, goal)` dựng chuỗi theo thứ tự ưu tiên, tự probe SDR
(pyrtsdr/SoapySDR/pylibiio), tự chọn LNA/BPF tốt nhất đang có, tính **T_sys,
SEFD, biên ADC, tốc độ ghi** và cảnh báo. Không có gì → dùng phương án dự phòng
và ghi rõ trong báo cáo:

```bash
python psr_hw.py        # in 3 chuỗi + trường hợp hỏng LNA ngoài (fallback)
```

Kết quả mẫu (423 MHz, có SPF5189Z + BPF): `T_sys = 132 K, SEFD = 61 kJy`.
Khi hỏng LNA ngoài (fallback LNA nội RTL): `T_sys ≈ 1000 K` — phần mềm giữ
hệ chạy nhưng **độ nhạy giảm ~8 lần**, cảnh báo in rõ.

Thư viện linh kiện (`psr_hw.PARTS`): SAWbird+HI, SPF5189Z, ZKL-33ULN-S+ (TNU),
LPF-450 (TNU), BPF 380–450 / 1300–1500, SAW 1420, RTL-SDR v5, RSP1A, Pluto+,
LimeSDR, USRP B210, bias-tee, GPSDO. Muốn thêm linh kiện: thêm dòng vào `PARTS`.

---

## 3. Ghi tự động 4–5 giờ không canh chừng (`record_unattended.py`)

Đúng yêu cầu: **channelize ngay → ghi phổ động**, không cần ai ngồi canh.

```bash
python record_unattended.py --selftest                  # test toàn chuỗi (không cần SDR)
python record_unattended.py --target B0950+08 --hours 4.5 --band 423 --analyze
python record_unattended.py --mock --seconds 12 --analyze   # chạy thử end-to-end
```

Đặc điểm kỹ thuật:

| Việc | Cách làm | Vì sao |
|---|---|---|
| Channelize ngay | FFT `nchan` mẫu → tích `navg` frame → 1 dòng phổ | 2.3 MB/s (IQ thô) → **~0.25 MB/s** (64 kênh × 256 µs) |
| Ghi tăng dần | `.fil` SIGPROC + `fsync` mỗi 512 dòng | mất điện chỉ mất block cuối |
| **Đếm mẫu** | so số mẫu SDR với đồng hồ treo | phát hiện mất mẫu USB (>5% → ghi gap log) |
| Sidecar JSON | UTC, chuỗi phần cứng + fallback, ppm, T_sys, SEFD, gap | metadata bắt buộc cho khoa học |
| Kiểm chứng đầu–ra | đọc lại file vừa ghi, đối chiếu số dòng/kênh/tsamp | PASS/FAIL ngay tại chỗ |
| Dừng êm | Ctrl+C → đóng file an toàn | |
| Phân tích liền | `--analyze` chạy `psr_detect` trên file vừa ghi | không cần thao tác tay |

Dung lượng 4.5 h: **~4 GB** (64 kênh × 256 µs, uint8). Đủ ổ cứng bình thường.

### 3b. Yêu cầu MỚI cho trình ghi (chưa triển khai — thuộc mốc M1/M2 của `docs/07`)

Bốn thay đổi **bắt buộc** để xử lí pha tuyệt đối và hiệu chuẩn dài hạn. Hiện trình
ghi chưa đáp ứng; ghi ở đây để không quên khi làm M1–M2:

| # | Yêu cầu | Vì sao (nếu thiếu thì hỏng gì) |
|---|---|---|
| 1 | **Log gap theo CHỈ SỐ MẪU**: `{after_row, missing_samples, t_rel_s, reason}` | Log theo giây không đủ để dựng lại pha tuyệt đối khi fold/cộng dồn nhiều đêm |
| 2 | **`segments[]`** (đoạn liên tục): `{i, first_row, rows, t_start_s}` | Xử lí theo đoạn thay vì zero-pad (xem `docs/07` §6.2) |
| 3 | **Bandpass theo khối 600 s**: lưu `scale[t]` **và** `channels_flagged[t]` | Trôi gain theo nhiệt độ trong 4.5 h; RFI xuất hiện giữa phiên |
| 4 | **Thời gian tuyệt đối**: `t0_mjd` + `ntp_offset_ms` (đầu và cuối phiên) | Không có thì P và pha không so được với catalogue; không cộng dồn đêm được |

Thêm (khuyến nghị): `adc_clip_frac` mỗi khối (RTL-SDR 8-bit dễ bão hoà vì CW mạnh
trong băng), `sha256` của file ghi, và `manifest.json` cho chính sách lưu trữ
(xem `docs/07` §10).

**Hợp đồng metadata cho tầng nhận dữ liệu** (`docs/07` §6c.1) — phải ghi ngay khi bắt
đầu phiên, nếu thiếu thì phần mềm phải suy ra và đánh dấu `inferred`:

```
stage            RAW_IQ | CHANNELIZED_POWER | DEDISPERSED_TS
hardware_id      rtlsdr_v5 | N6002 | ...
adc_bits         8
sample_rate_hz   2400000
center_freq_hz   1420000000
calibrated       true/false        (đã làm phẳng bandpass chưa)
time_sync        GPS_PPS | NTP | LOCAL_CLOCK
telemetry        {t_lna_c, t_rack_c, adc_clip_frac, tsys_k, y_factor_ts}
```

Cảm biến nhiệt LNA/rack là **tuỳ chọn nhưng nên có**: thiếu nó thì không bù được trôi
gain và không gắn được tag `GAIN_DRIFT`.

---

## 4. Những lỗi THẬT đã gặp và sửa — đọc để không lặp

Trong quá trình chạy trên dữ liệu thật (GREENBURST/GBT, B0329+54), pipeline
đã fail kiểm chứng **nhiều lần** trước khi đúng. Đây là danh sách đầy đủ:

| # | Lỗi | Triệu chứng | Cách sửa |
|---|---|---|---|
| 1 | `zero_dm_excise` cắt **cả xung tán sắc** | DM scan rơi vào 45.25 vô nghĩa; 1110 mẫu bị cắt = đúng 3 vệt xung | chỉ cắt khi phần thừa **phẳng trên phổ** (RFI); giữ khi tập trung theo tần số |
| 2 | Đo DM bằng trọng tâm bị **nhiễu dương kéo lệch** | DM đo 24–25 thay vì 26.76 | thay bằng đỉnh lọc khớp + nội suy parabol |
| 3 | Dải 1020 MHz bị **trải nội dải 26 ms** làm mờ đỉnh | trễ đo lệch −7 ms | khử tán sắc **nội dải** trước khi đo đỉnh |
| 4 | Dải 1860 MHz (GSM/LTE) cho **đỉnh RFI giả** | DM fit lệch | khớp có **sigma-clip** + trọng số SNR |
| 5 | Lỗi `tsamp`/`tsamp_s` bị **câu `except` nuốt** | 0/26 xung mà không thấy lỗi | in exception ra log; không bao giờ nuốt lỗi im lặng |
| 6 | Dịch kênh khi vẽ waterfall **đảo dấu** | vệt "đã khử tán sắc" vẫn cong | `out[j] = in[j+shift]` (dịch sớm), không phải `in[j−shift]` |
| 7 | Quét DM kiểu xung đơn **mù** với dữ liệu yếu | mock 12 s: DM scan 51.5 rác | khi biết P: quét DM bằng **fold** (nhạy hơn nhiều) |
| 8 | `subband_dm_single` trả **DM rác** khi gọi sai thời điểm | test fail nhưng không rõ vì sao | ngưỡng SNR dải con ≥ 5, nếu không `raise` |
| 9 | Numpy bool trong JSON | crash khi ghi metrics | bộ `_jsonify` chuẩn hoá trước khi dump |
| 10 | FFT xếp hạng **hạng 1 là nhiễu** (bản đầu) | f0 thật ở hạng 3 | mọi ứng viên FFT phải kiểm chứng bằng fold |

Bài học xuyên suốt: **bộ kiểm chứng đầu–ra (`output_checks`) chính là thứ phát
hiện tất cả lỗi trên**. Không có nó, pipeline vẫn "chạy" và cho số sai.

---

## 5. Kết quả trên dữ liệu THẬT (GREENBURST/GBT, B0329+54)

File: `data/B0329+54.fil` (4096 kênh, 960–1920 MHz, 256 µs, 2.1 s — "Greenburst
cutout of three pulses from B0329+54", Joseph W Kania, Zenodo 5570222, CC-BY-4.0).

```bash
python psr_detect.py        # → results/B0329+54_fig1/fig2, _detect_metrics.json, _report.txt
```

Kết quả cuối (tất cả kiểm chứng PASS):

| Đại lượng | Đo được | Tham chiếu (ATNF) | Đánh giá |
|---|---|---|---|
| Số xung | **3 xung cùng pha 293.7 ± 0.6 ms** (mod P = 714.5 ms) | "three pulses" | ✅ xác nhận pulsar |
| DM | **25.98 ± 0.50** (trễ dải con, có trọng số SNR) | 26.7641 | ✅ lệch 0.78, trong ngưỡng |
| DM (quét fold) | 27.25 (đỉnh 608σ) | 26.7641 | ✅ |
| SNR xung mạnh nhất | **608** (lọc khớp boxcar) | — | |
| Bề rộng xung | 8.2 ms @1.9 GHz | W50 ≈ 6–12 ms | ✅ |
| Đối chứng nền (xáo trộn từng kênh) | 9.2σ | phải < 12 | ✅ không có phát hiện giả |
| Ứng viên bị loại | 21 (RFI hẹp băng, DM dải con vô nghĩa) | — | bộ lọc nhất quán DM hoạt động |

Kết luận: pipeline phát hiện pulsar trên **dữ liệu kính thiên văn thật**, đo
đúng DM trong sai số cho phép, tự loại RFI, và tự xác nhận bằng **tính cùng pha**.

---

## 6. Quy trình vận hành "để đó về" (unattended night)

1. **Ban ngày / trước buổi**: `python psr_targets.py --transit` → xem giờ transit,
   trỏ chảo theo (az, el) gợi ý (hoặc để nguyên nếu đã trỏ từ đêm trước).
2. **Khởi động**: `python record_unattended.py --target B0950+08 --hours 4.5 --band 423`
   → chuỗi phần cứng tự chọn + fallback, ghi `data/<ngày>/<target>.fil` + `.json`.
3. **Để đó** — heartbeat in mỗi phút; mất mẫu được ghi vào gap log; Ctrl+C khi muốn dừng.
4. **Sáng hôm sau**: `python psr_detect.py --file data/<ngày>/<target>.fil
   --dm-ref 2.97 --p 0.253065` → báo cáo + biểu đồ.
5. **Nhiều đêm**: chạy lại 2–3 đêm, `psr_swcomp.stack_profiles()` cộng dồn
   hồ sơ → SNR ∝ √(số đêm).

Lịch mùa + mục tiêu: xem `docs/05` §8 (B0950+08 tháng 2, Vela tháng 1...).

---

## 7. Giới hạn trung thực của cấu hình tối giản

- **M0 (không mua gì)**: B0950+08 cần 4–8 đêm × 2.5 h để đạt SNR ~7–8. Được,
  nhưng chỉ với mục tiêu **sáng nhất**; đừng kỳ vọng B0329+54/Vela.
- Không BPF ở TP.HCM: FM 88–108 + DVB-T có thể **bão hoà ADC** — phần mềm không
  cứu được clipping. BPF 380–450 MHz là món **duy nhất bắt buộc mua** (~1–2 tr).
- Không GPSDO: fold từng đêm riêng (P catalogue chính xác ~1e-10) — **không**
  cộng dồn TOA nhiều tháng; để đó cho giai đoạn 4.
- Transit không motor: chỉ ~40–55% thời gian treo hữu ích (đã tính trong
  `T_eff`), nhưng **0 phút canh chừng** — đổi đúng thứ người dùng cần.

---

## 8. Kiểm chứng giao diện: bấm từng nút, kiểm tra từng đường dẫn

```bash
cd code && python gui_verify.py      # 37 kiểm tra, ~2–4 phút
```

Bộ kiểm chứng **tự bấm** mọi nút (không cần người) và xác nhận sản phẩm ra đúng
chỗ. Kết quả hiện tại: **37/37 PASS**. Nó đã phát hiện **6 lỗi thật** trong GUI:

| # | Lỗi | Triệu chứng | Sửa |
|---|---|---|---|
| 1 | `root.after()` gọi từ thread phụ | `RuntimeError: main thread is not in main loop` → **sập app** khi tác vụ xong | thêm hàng đợi `cbq`: thread phụ `post(callable)`, main thread thực thi |
| 2 | Lambda trong worker đọc widget (`self.tgt_date.get()`) | nút "Giờ transit"/"Ban ngày" **không ra gì** (Tkinter cấm đọc widget ngoài main thread) | đọc giá trị ở main thread rồi mới phóng xuống nền |
| 3 | Tab "Mục tiêu" in ra nhật ký chung | 5 nút đổ kết quả sai chỗ, bảng của tab trống | thêm `run_into()` gom stdout vào đúng widget |
| 4 | `open_dir()` tự `makedirs` | bấm nhầm sinh thư mục rác `results/data/` | chỉ mở, không tạo; báo lỗi nếu chưa có |
| 5 | Sidecar `.json` ghi **trước** kiểm chứng | metadata thiếu `roundtrip_ok` → không biết file có hỏng | chuyển sang ghi **sau** khi đọc lại file |
| 6 | Mock mode sinh cả mảng | đặt 1.0 h → cấp phát ~3.6 GB RAM (treo/khớp) | `MockStream` sinh **từng dòng** O(nchan) + giới hạn 180 s mô phỏng |

Ngoài ra còn một lỗi **thiết kế kiểm chứng**: ở `B = 2.4 MHz` độ phân giải DM là
`±38`, không thể phân biệt DM nào → kiểm chứng DM từng báo FAIL oan. Nay
`psr_detect` tự nhận biết: nếu `dm_res_data > 25% DM tham chiếu` thì ghi
**"KHÔNG ÁP DỤNG"** kèm giải thích, thay vì FAIL.

### Những gì bộ kiểm chứng xác nhận

| Nhóm | Nội dung |
|---|---|
| Đường dẫn | `data/`, `results/` nằm trong thư mục app; file dữ liệu thật tồn tại; mỗi lần chạy một thư mục `results/<tên dữ liệu>/` hoặc `<ngày>/` |
| Tab 2 | mở hộp chọn file đúng `data/`, chạy phát hiện, ra đủ 4 file, dropdown ảnh dạng `thư-mục/tên`, vẽ được vào khung, 3 nút "Mở …" mở đúng đường dẫn |
| Tab 1 | ghi ra `data/<ngày>/*.fil` + `.json` (có `roundtrip_ok`, gap log), "Phân tích file vừa ghi" tạo `results/<tên file ghi>/`, nút **Dừng** đóng file an toàn |
| Tab 3 | cả 5 nút đổ bảng vào đúng panel của tab (959 / 846 / 5025 / 1137 / 1470 ký tự) |
| Tab 4 | chuỗi linh kiện ra `T_sys`/`SEFD`, tự kiểm tra công thức OK |
| Tab 5 | selftest 21/21 trong GUI, pipeline mô phỏng, test trình ghi |
| An toàn | **không** file nào bị ghi/mở ra ngoài thư mục app |

---

## 9. Corpus dữ liệu "XẤU" — kiểm chứng trên dữ liệu thật đủ kiểu lỗi

Yêu cầu: **tìm dữ liệu pulsar thô, càng xấu càng tốt, tải về và test.** Corpus
nằm trong `data/stress/` (tải từ 2 nguồn CC-BY / public), chạy:

```bash
cd code && python stress_test.py          # 9 file, ~2–4 phút
```

| File | Xuất xứ | Kiểu "xấu" | Kỳ vọng | Kết quả |
|---|---|---|---|---|
| `tutorial.fil` | sigpyproc (ví dụ chính thức) | **mẫu 2-BIT đóng gói**, chỉ 69 MHz | detect | ✅ **SNR 112.9**, DM 31.5 |
| `injected_B0531.fil` | tự tạo từ nền Crab thật | pulsar tiêm vào **nền RFI thật** | detect | ✅ **SNR 21.8**, DM 56.5 (thật 56.77) |
| `B0531+21.fil` | Zenodo 5875992 (paper IQRM) | Crab, 336 MHz, RFI dày | nodetect | ✅ không báo phát hiện (SNR 5.1) |
| `B1828.fil` | Zenodo 5875992 | 4096 kênh, RFI xung, 67 MB | nodetect | ✅ không báo phát hiện (SNR 6.7) |
| `empty_example.fil` | Zenodo 5875992 | **CHỈ RFI** (đối chứng âm) | nodetect | ✅ **veto đúng** (SNR 963 nhưng bị nhận là zero-DM) |
| `28.fil` | P→YOUR tests | 6.5 s, 49 kênh RFI | any | ✅ chạy sạch |
| `small.fil` | P→YOUR tests | **10 mẫu** (file cụt) | reject | ✅ `too_short`, không crash |
| `test_4pol.fits` | P→YOUR tests | **PSRFITS hỏng**: thiếu NPOL, 200 mẫu | reject | ✅ đọc được (suy NPOL=4) rồi `too_short` |
| `empty.fits` | P→YOUR tests | **PSRFITS rỗng** (NAXIS2 = 0) | reject | ✅ `unreadable` + chẩn đoán rõ |

**9/9 hành xử đúng kỳ vọng.** Báo cáo: `results/stress_report.txt` + `stress_matrix.json`.

### Tải lại corpus (nếu xoá `data/stress/`)

```text
https://zenodo.org/api/records/5875992/files/empty_example.fil/content   (33.5 MB)
https://zenodo.org/api/records/5875992/files/B0531+21.fil/content        (11.0 MB)
https://zenodo.org/api/records/5875992/files/B1828.fil/content           (67.1 MB)
https://raw.githubusercontent.com/thepetabyteproject/your/main/tests/data/28.fil
https://raw.githubusercontent.com/thepetabyteproject/your/main/tests/data/small.fil
https://raw.githubusercontent.com/thepetabyteproject/your/main/tests/data/test_4pol.fits
https://raw.githubusercontent.com/thepetabyteproject/your/main/tests/data/empty.fits
https://raw.githubusercontent.com/ewanbarr/sigpyproc/master/examples/tutorial.fil
```
(`injected_B0531.fil` do `stress_test.py` tự sinh từ nền Crab — 44 MB, xoá được.)

### 6 lỗi thật + 1 lỗi thiết kế đã bị corpus phát hiện

| # | Lỗi | Bằng chứng | Sửa |
|---|---|---|---|
| 1 | Thiếu khoá header `barycentric`, `pulsarcentric` | **3/6 file .fil không đọc được** ngay từ đầu | bổ sung vào `_I32_KEYS` |
| 2 | Không hỗ trợ **mẫu 1/2/4-bit** | `tutorial.fil` (2-bit) bị từ chối | `_unpack_bits()` giải mã MSB-first |
| 3 | Không hỗ trợ **nifs > 1** | `test_4pol.fits` (4 phân cực) | cộng/chọn phân cực, `pol='sum'/'first'/số` |
| 4 | **Không có bộ đọc PSRFITS** | mọi dữ liệu Parkes/GBT/FAST đều bị từ chối | `psr_fits.py` (kèm `write_psrfits` để tự test) |
| 5 | FITS `I` = **int16 CÓ DẤU** | ghi 32768 → đọc ra −32768, sai 8192 đơn vị | ghi int16 + `DAT_SCL/OFFS` đúng |
| 6 | **RFI lọt qua** → dương tính giả SNR 963 | `empty_example.fil` được báo "26 xung nhất quán DM" | `mask_bursty_channels` (P99.9/median), `zero_dm_filter` (trừ common-mode), **zero-DM veto** (SNR(DM=0) ≥ 0.87·SNR_đỉnh ⇒ RFI) |
| 7 | Thiếu khoá header tuỳ chọn làm **crash** | `test_4pol.fits` → `KeyError: 'tstart'` | dùng `.get()` cho mọi khoá tuỳ chọn |
| 8 | Gộp kênh quá tay (64 → 8 kênh) | mất độ phân giải DM | giữ **≥128 kênh** khi quét DM |

### Bài học lớn nhất

**File "Crab" và "B1828" trong bộ IQRM KHÔNG chứa tín hiệu pulsar** — đo tại đúng
P và DM catalogue chỉ được SNR 3.3 / 8.1. Chúng là mẫu RFI của paper. Kỳ vọng ban
đầu của tôi ("phải detect") là **sai**; pipeline đã đúng khi **không** báo phát hiện.
Đây là lý do phải có **ca tiêm (injection)**: nó chứng minh pipeline vẫn tìm được
tín hiệu thật *khi có* tín hiệu, ngay trong nền RFI đó.

### Về "dương tính giả"

`empty_example.fil` cho SNR 963 (RFI 10 Hz băng rộng). Sau khi thêm zero-DM veto,
pipeline báo `status = rfi_zero_dm` và **không** tạo chuỗi xung. Lưu ý trung thực:
**SNR 963 vẫn hiện trong báo cáo** — ta không "giấu" nó, ta chỉ kết luận đúng bản
chất. Mọi báo cáo đều in rõ: `SNR(DM=0)`, `SNR(đỉnh)`, tỷ số, và lý do veto.

---

## 10. Dữ liệu **IQ THÔ** (chưa channelize) — đúng "từ dây signal vào máy"

Toàn bộ phần trên làm việc với *phổ động* (đã channelize). Nhưng đường đi thật của
tín hiệu là: **dây/feed → SDR/backend → cặp mẫu I/Q → FFT → kênh tần số**. Để kiểm
chứng trọn chuỗi, ta phải tự làm bước A1 từ dữ liệu thô.

### 10.1 Định dạng đọc được (`code/psr_iq.py`)

| Định dạng | Đuôi / cách nhận | Ghi chú |
|---|---|---|
| **SigMF** | `.sigmf-data` + `.sigmf-meta` | `ci8 / ci16_le / ci16_be / cf32` — chuẩn của ATA, CAMRAS, nhiều SDR |
| SDR thô | `.cu8 .cs8 .cs16 .ci16 .cf32 .iq .bin` | rtl_sdr, GQRX, SDR# |
| WAV I/Q | `.wav` 2 kênh 8/16-bit | máy thu nghiệp dư |
| NumPy | `.npy` (mảng phức) | để tự kiểm thử |

Xử lý bắt buộc với IQ thật (đều đã cài trong `fix_iq()` + `channelize_iq()`):

1. **DC spike** — trừ trung bình phức (SDR nào cũng có gai ở tần số tâm).
2. **Mất cân bằng I/Q** (biên độ + pha) — gây **ảnh gương** ở −f; ước lượng bằng
   Gram-Schmidt: `a = <I'Q'>/<I'I'>`, `Q'' = Q' − a·I'`, chuẩn hoá lại biên độ.
3. **Channelize**: FFT N điểm có cửa sổ Hann → công suất → chuẩn hoá để nhiễu trắng
   trung bình 1 → hoán vị Nyquist về thứ tự tần số tăng.
4. Gộp `navg` khung → `tsamp = nchan·navg/fs`.

### 10.2 Dữ liệu THẬT đã tải: giant pulse Cua, kính Dwingeloo 25 m

`data/iq/crab-giantpulse.sigmf-data` — **16 MB, `ci16_le`, 20 MS/s, tâm 410 MHz,
0.2 s** (Fine, Dijkema & Hessels 2024, Zenodo 13143544, CC-BY-4.0). Đây là **IQ thô**,
chưa qua bất kỳ bộ channelize nào.

```bash
python psr_detect.py --file ../data/iq/crab-giantpulse.sigmf-data --dm-ref 56.77
```

Kết quả trên máy này:

| Bước | Kết quả |
|---|---|
| Đọc IQ | 4 000 000 mẫu phức @ 20 MS/s, tâm 410 MHz, 0.200 s |
| Sửa méo IQ | DC 0.21, tỉ số biên độ I/Q **0.996**, sin pha 0.001 (thiết bị tốt) |
| Channelize | **256 kênh × 976 mẫu**, 400–420 MHz, `tsamp` 204.8 µs |
| Quét DM | đỉnh **108.3σ tại DM = 56.75** (Crab: 56.77) ✔ |
| So với DM = 0 | 3.8σ → tỉ số **19×** ⇒ tín hiệu **có tán sắc thật** |
| Xung | 1 giant pulse tại t = 27.3 ms, rộng 0.8 ms, SNR 108 |
| DM dải con (A11c) | **56.71** (lệch 0.06 so với catalogue) |
| Kết luận | `status = ok`, 5/5 kiểm chứng PASS |

> Đây là bằng chứng mạnh nhất từ đầu dự án: **từ mẫu điện áp thô → FFT → khử tán sắc
> → đo DM → phát hiện**, không dùng bất kỳ phổ động dựng sẵn nào.

### 10.3 Muốn tải thêm IQ thô ở đâu?

| Nguồn | Có gì | Ghi chú |
|---|---|---|
| **Zenodo 13143544** | Crab giant pulse, Dwingeloo, 0.2 s, `ci16` ✅ đã tải | nhỏ, đúng chủ đề |
| Zenodo — tìm `"sigmf" pulsar`, `"baseband"`, `"voltage"` | vài ca lẻ | dùng từ khoá tiếng Anh |
| **Breakthrough Listen Open Data** (`seti.berkeley.edu/opendata`, `blimpy`) | filterbank + một số `.h5` (đã channelize) | tải qua `blimpy.fetch` |
| ATA / CAMRAS SigMF collections | SigMF `.sigmf-data` | đa số là tín hiệu không phải pulsar |
| **Tự ghi bằng RTL-SDR** | IQ thô của chính kính mình | xem §10.4 |

Lưu ý thực tế: **IQ thô của pulsar rất hiếm trên mạng** vì dung lượng lớn
(20 MS/s × 16-bit × 2 = 80 MB/s). Đa số dữ liệu công bố đã channelize thành
filterbank/PSRFITS. Vì vậy đường đúng là: **tự ghi IQ** từ SDR của mình.

### 10.4 Tự ghi IQ thô bằng RTL-SDR (1 dòng lệnh)

```python
from rtlsdr import RtlSdr
s = RtlSdr(); s.sample_rate = 2.4e6; s.center_freq = 423e6; s.gain = 38
iq = s.read_samples(2_400_000)          # 1 giây, mảng phức
s.close()
from psr_iq import write_sigmf
write_sigmf("data/iq/423MHz_1s", iq.real*30000 + 1j*iq.imag*30000,
            2.4e6, 423e6, "cu8", "RTP-3.7 test capture")
```

Sau đó: `python psr_detect.py --file data/iq/423MHz_1s.sigmf-data --nchan-iq 128`
(hoặc mở bằng GUI: tab 2 → chọn file → đặt "IQ → kênh" → Chạy).

**Giới hạn phải biết**: 1 giây IQ ở 2.4 MS/s = 4.8 MB, nhưng 4.5 giờ IQ = **78 GB**.
Vì thế chế độ ghi tự động (§3) channelize ngay rồi mới ghi (0.25 MB/s) — IQ thô chỉ
dùng để *kiểm chứng* hoặc khi cần khử tán sắc **kết hợp** (A3, cần mẫu liên tục).

### 10.5 Bảng trạng thái chuỗi đầy đủ

```
dây → feed → LNA → SDR → [IQ thô] → channelize → [phổ động] → RFI → DM → fold → kết quả
                          ✅ đã test (psr_iq)   ✅ đã test (psr_core/psr_detect)
```

---

## 11. NGHIỆM THU trước khi đưa vào sử dụng (`acceptance_test.py`)

```bash
cd code && python acceptance_test.py          # 61 mục, ~70 s
python acceptance_test.py --only S3           # chỉ nhóm đầu ra
```

Nguyên tắc: **không chỉ kiểm "chạy được"**, mà kiểm cả **hành vi khi hỏng** —
vì đó mới là thứ quyết định có dùng được ngoài thực địa hay không.

| Nhóm | Nội dung | Kết quả |
|---|---|---|
| **S1 Đầu vào** (17) | fil 8/32-bit, fil 2-bit, file **cụt**, chỉ-header, **phẳng**, 0 byte, `nifs=2`, PSRFITS, IQ SigMF ci16/cu8/cf32, WAV, npy, sai đuôi, không tồn tại, truyền thư mục | **17/17** |
| **S2 Fallback** (10) | chuỗi 423/1420/HI, **hỏng LNA → T_sys 1628 K + cảnh báo**, tự kiểm công thức, **không có SDR → tự chuyển mô phỏng**, round-trip, sidecar đủ khoá, **Dừng giữa chừng**, mất mẫu → gap log | **10/10** |
| **S3 Đầu ra** (13) | gom 1 thư mục theo tên dữ liệu, đủ 4 tệp, JSON hợp lệ, **báo cáo khớp JSON**, PNG > 20 KB, tên có dấu cách/unicode/dài 120 ký tự, input hỏng **không sinh ảnh giả**, chạy lại không rác, **không ghi ra ngoài**, **thư mục chỉ-đọc** | **13/13** |
| **S4 GUI** (14) | 5 tab/22 nút, chưa chọn file, file không tồn tại, **DM nhập chữ**, **đang bận thì nút khác bị từ chối**, Dừng bật/tắt đúng, mở thư mục không tồn tại, chạy phát hiện thật, đổi ảnh, đóng app sạch | **14/14** |
| **S5 Đối chiếu** (7) | selftest 22, **IQ thật Dwingeloo: DM 56.71 vs 56.77**, SNR 108, corpus xấu 10/10, `gui_app --selfcheck`, **`PulsarObs.exe --selfcheck`**, EXE báo `frozen=True` | **7/7** |

**Tổng: 61/61 ĐẠT.** Biên bản: `results/acceptance_report.txt`.

### 7 lỗi thật do nghiệm thu phát hiện (đã sửa)

| # | Lỗi | Điều kiện kích hoạt |
|---|---|---|
| 1 | File **cụt giữa dòng** bị bỏ im lặng | cắt 97 byte cuối file |
| 2 | **WAV/NPY bị đọc như JSON** | mở `.wav`/`.npy` (UnicodeDecodeError) |
| 3 | Hỏng LNA chỉ đổi số, **không cảnh báo** | `have={"lna": "rtl_internal"}` → T_sys 1628 K |
| 4 | **Không có SDR → crash** thay vì fallback | `mock=False` khi chưa cắm thiết bị |
| 5 | Guard "quá ngắn" theo số mẫu → **giant pulse 0.2 s bị chặn** | file 976 mẫu |
| 6 | Nới guard theo mẫu → **file 4 ms lọt qua** | `test_4pol.fits` 200 mẫu |
| 7 | `--selfcheck` bản đóng gói **quá nông** (chỉ 8 mục) | không kiểm IQ/PSRFITS/xuất file |

### Ba chế độ nguồn dữ liệu (mục tiêu + SDR)

**Người dùng không phải nhớ bật/tắt gì.** Ô "Nguồn dữ liệu" ở tab 1 có 3 chế độ,
mặc định là *Tự động*:

| Chế độ | Hành vi | Dùng khi nào |
|---|---|---|
| **Tự động** (mặc định) | Mở app và mỗi lần bấm ghi đều dò USB/driver: **có SDR → thu thật**, không có → **mô phỏng** kèm cảnh báo 🟡 và `mode="fallback-mock"` trong JSON | Quan sát hằng ngày — cắm dây là chạy |
| **Bắt buộc MÔ PHỎNG** | Luôn mô phỏng, **không mở** thiết bị (không chiếm SDR) | Thử pipeline khi SDR vẫn đang cắm trên bàn |
| **Bắt buộc SDR THẬT** | Không có/mất SDR → **báo lỗi và dừng**, tự thử kết nối lại 8 lần, **tuyệt đối không ghi dữ liệu giả** | Treo máy 4–5 giờ qua đêm |

Nhãn trạng thái cạnh nút ghi: 🟢 *RTL-SDR (R820T2): đã kết nối* · 🟡 *Tự động →
MÔ PHỎNG* · 🔴 *KHÔNG có SDR* — kèm nút **Làm mới** để dò lại sau khi cắm dây.
Lý do chọn chế độ 3: nếu giữa đêm USB lỏng mà app âm thầm chuyển sang mô phỏng thì
buổi quan sát **hỏng mà không ai biết**.

### Mục tiêu không bị khoá cứng

Ô "Mục tiêu" **gõ tay được** và có nút **＋ Mục tiêu…** để thêm/sửa/xoá mục tiêu
ngoài danh mục (pulsar mới, nguồn continuum, mục tiêu tự đặt). Nhập tên, RA, Dec
(`HH:MM:SS` → hiểu là giờ; chỉ số → độ), P, DM, flux, W50 (các ô sau bỏ trống được).
Lưu ở `targets_user.json` cạnh ứng dụng; mục tiêu tự thêm xuất hiện ngay trong
danh sách, trong bảng SNR và trong tra cứu DM tham chiếu của tab 2.

### Điều nghiệm thu KHẲNG ĐỊNH được

- **Fallback đúng như yêu cầu**: ở chế độ *Tự động*, cắm dây vào mà SDR không mở
  được → app **tự chuyển chế độ mô phỏng**, ghi rõ lý do (`LibUSBError…`) vào log
  **và** sidecar JSON (`mode="fallback-mock"`, `fallback="…"`), dữ liệu vẫn ghi
  đúng định dạng và đọc lại được. Người dùng không bị mất buổi quan sát.
- **Chế độ *Bắt buộc SDR thật* thì KHÔNG fallback**: không có thiết bị → `RuntimeError`
  và không tạo file; mất kết nối giữa phiên → ghi `sdr_errors`, `aborted`, đóng file
  an toàn và giữ dữ liệu đã ghi.
- **Mọi nút đều có tác dụng thật** và **không nút nào làm treo app**, kể cả khi
  bấm sai thứ tự, khi đang chạy job khác, hay khi đường dẫn không tồn tại.
- **Xuất file chính xác**: đúng 1 thư mục/lần chạy, 4 tệp, số trong báo cáo **khớp**
  số trong JSON, không sinh ảnh khi không có phát hiện, không ghi ra ngoài app.
- **Bản đóng gói (EXE) tự chứng minh**: `PulsarObs.exe --selfcheck` chạy 7 phép
  kiểm bên trong chính nó (import, IQ→channelize, PSRFITS round-trip, phát hiện +
  xuất 4 tệp, JSON hợp lệ, selftest) và báo `frozen = True`.
