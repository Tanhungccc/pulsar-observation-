# Pulsar Observation — RTP-3.7 (TP.HCM)

Thư mục làm việc riêng cho chương trình **quan sát pulsar** bằng kính POAM RTP-3.7
(3.7 m, L-band). Chứa: nghiên cứu vật lý – thuật toán, ngân sách S/N thực tế của
kính, danh mục mục tiêu, kế hoạch triển khai có cổng quyết định, **và bộ code DSP
chạy được + đã kiểm chứng**.

```
pulsar observation/
├── PulsarObs.exe                   ★ GIAO DIỆN một-click (tải từ Releases, không nằm trong repo)
├── build_exe.bat                   (tuỳ chọn) chỉ để TỰ BUILD lại EXE
├── README.md                       ← file này
├── TNU SUMMER SCHOOL 2026...pdf    báo cáo thực nghiệm 2.4 m @423 MHz (đối chiếu: docs/02 §4.3)
├── docs/
│   ├── 01_vat_ly_va_thuat_toan.md  vật lý tín hiệu + 13 thuật toán (A1–A13)
│   ├── 02_chuoi_thu_va_do_nhay.md  chuỗi thu, T_sys, SEFD, ngân sách S/N, RFI
│   ├── 03_do_duoc_gi_tu_pulsar.md  đo được gì: P, Ṗ, B, tuổi, DM, vị trí, ...
│   ├── 04_quan_sat_gi_khac.md      còn quan sát được gì khác ngoài pulsar
│   ├── 05_ke_hoach_trien_khai.md   kế hoạch 5 giai đoạn + cổng G0–G4 + chi phí
│   ├── 06_phan_cung_toi_gian_va_ghi_tu_dong.md  phần cứng tối giản, ghi tự động, nghiệm thu
│   ├── 07_kien_truc_he_thong_xu_ly.md  ★ ĐẶC TẢ CHỐT kiến trúc 6 tầng + mốc M1–M5
│   ├── 08_nghien_cuu_kha_thi.md     làm được gì về pulsar với thiết bị hiện có (kèm arXiv)
│   └── 09_ho_so_thiet_bi_rtp37.md  ★ HỒ SƠ THIẾT BỊ THỰC TẾ (chảo, feed, tủ rack, RTCS, số đo)
├── code/
│   ├── psr_core.py                 lõi DSP (tán sắc, fold, FFT, RFI, SNR, DM)
│   ├── psr_fil.py                  đọc/ghi SIGPROC .fil (1/2/4/8/16/32-bit, nifs>1)
│   ├── psr_fits.py                 đọc PSRFITS (+ ghi PSRFITS tối thiểu để tự test)
│   ├── psr_iq.py                   đọc IQ THÔ (SigMF/SDR/WAV) + channelize + sửa méo IQ
│   ├── psr_detect.py               pipeline phát hiện trên DỮ LIỆU THẬT (.fil)
│   ├── psr_plots.py                biểu đồ chuẩn (nhãn + đơn vị + chú giải đúng)
│   ├── psr_hw.py                   mô hình phần cứng: dự đoán chuỗi + tự fallback
│   ├── psr_rtcs.py                 ★ đọc dữ liệu xuất RTCS (phổ/continuum/scan),
│   │                               khớp Gauss tính HPBW, hiệu chuẩn Appendix A
│   ├── psr_swcomp.py               bù trừ bằng phần mềm (ppm, transit, stacking…)
│   ├── record_unattended.py        GHI TỰ ĐỘNG 4–5 giờ không cần canh chừng
│   ├── psr_sim.py                  sinh dữ liệu pulsar tổng hợp (kiểm chứng)
│   ├── psr_sensitivity.py          SEFD / gain / SNR (ngân sách S/N)
│   ├── psr_targets.py              danh mục, quan sát ban ngày/transit, đại lượng suy ra
│   ├── psr_pipeline.py             pipeline end-to-end trên dữ liệu tổng hợp
│   ├── acceptance_test.py          ★ NGHIỆM THU: 61 mục (S1–S5), 61/61 ĐẠT
│   ├── stress_test.py              CORPUS dữ liệu XẤU: 10 file, 10/10 PASS
│   ├── gui_verify.py               kiểm chứng GUI: tự bấm mọi nút, 37 kiểm tra
│   ├── gui_app.py                  GIAO DIỆN 5 tab (Tkinter) — nguồn của EXE
│   └── selftest.py                 22 test kiểm chứng vật lý + thuật toán
├── data/
│   ├── B0329+54.fil                DỮ LIỆU THẬT: GREENBURST/GBT, 3 xung B0329+54
│   ├── stress/                     CORPUS "XẤU": Crab, RFI, 2-bit, PSRFITS hỏng…
│   ├── iq/                         IQ THÔ THẬT: giant pulse Cua, Dwingeloo 25 m
│   └── <YYYYMMDD>/                 file ghi tự động (<target>_<UTC>.fil + .json)
└── results/
    ├── <tên_file_dữ_liệu>/         ★ MỖI LẦN CHẠY MỘT THƯ MỤC: fig1, fig2, metrics, report
    ├── <YYYYMMDD>/                 pipeline mô phỏng (không có tên file → tên ngày)
    └── _logs/                      log + bảng CSV/TXT xuất từ các công cụ
```

---

## 0. Tải nhanh (không cần Python)

Tải **`PulsarObs.exe`** từ trang Releases:
**https://github.com/Tanhungccc/pulsar-observation-/releases/latest**

Double-click để mở. Repo **không chứa dữ liệu quan sát** — tải theo `DATA_SOURCES.md`.

**Phiên bản mới nhất: 1.6.0.**

### Hình vẽ: mỗi hình xuất 3 định dạng

Mỗi lần chạy, thư mục `results/<YYYYMMDD_HHMMSS>/` có **cùng một hình ở 3 đuôi**:

| Tệp | Dùng để | Đặc điểm |
|---|---|---|
| `figN_*.png` | xem nhanh trong app, chèn vào báo cáo ngắn | ảnh raster 200 dpi — **phóng to sẽ vỡ nét** (dùng SVG khi cần soi) |
| `figN_*.svg` | **zoom vô hạn** (mở bằng Edge/Chrome/Inkscape) | vector, chữ chọn/copy được, nhẹ hơn PNG |

Quy ước ký hiệu (mỗi ký hiệu đều có trích dẫn bài báo) và cách tương tác
zoom/pan/thanh trượt: xem [`docs/10_quy_uoc_hinh.md`](docs/10_quy_uoc_hinh.md).

Trong Tab 2 có nút **“Mở SVG (zoom ∞)”** để mở bản vector của hình đang chọn, và thanh
công cụ matplotlib (**zoom khung / pan / lưu**) ngay dưới khung hình. Lưu ý: zoom thanh
công cụ là phóng ảnh đã vẽ; muốn xem chi tiết tới từng điểm dữ liệu thì dùng **SVG/PDF**.

## 0b. Trạng thái & lộ trình phần mềm

Baseline hiện tại đã kiểm chứng xong (selftest 23/23, gui 48/48, nghiệm thu 67/67).
Bản nâng cấp **đã chốt thiết kế nhưng CHƯA triển khai** — xem
**`docs/07_kien_truc_he_thong_xu_ly.md`**:

| Mốc | Nội dung |
|---|---|
| **M1** | Hồ sơ trạm/kính (`psr_site`) + module hằng số (`psr_constants`) — refactor không đổi hành vi |
| **M2** | Dò DM 2 tầng + đọc theo khối (file 4 GB, RAM < 2 GB) |
| **M2.5** | **Injection–recovery** — cổng bắt buộc, sinh `capability_matrix.md` |
| **M3** | Dò chu kỳ mù + danh sách ứng viên |
| **M4** | Chế độ quan sát `fixed` / `track` + pointing log |
| **M5** | CLI `pulsarobs` + `report.json` schema v3 + `export-pac` |

## 1. Mở giao diện (cách dễ nhất)

**Double-click `PulsarObs.exe`** — không cần cài Python.

5 tab: **Ghi tự động** · **Phát hiện** · **Mục tiêu** · **Phần cứng** · **Kiểm chứng**.
Kiểm tra bản đóng gói: `PulsarObs.exe --selfcheck` → ghi `selfcheck_report.txt`.

**Người dùng chỉ cần `PulsarObs.exe`** — không cần file `.bat`.
`build_exe.bat` chỉ dành cho người sửa code: chạy nó để đóng gói lại
(~2–3 phút, ra `PulsarObs.exe`).

## 1b. Chạy bằng dòng lệnh

```bash
cd "pulsar observation/code"
python gui_app.py             # mở giao diện từ mã nguồn (thay vì EXE)
python gui_verify.py          # KIỂM CHỨNG GUI: tự bấm mọi nút, 37 kiểm tra
python acceptance_test.py     # ★ NGHIỆM THU 61 mục: đầu vào/fallback/đầu ra/GUI/EXE
python stress_test.py         # CORPUS DỮ LIỆU XẤU: 10 file (gồm IQ thô), PASS
python psr_detect.py --file ../data/iq/crab-giantpulse.sigmf-data --dm-ref 56.77
python selftest.py            # phải ra 22/22 PASS (~10 s)
python psr_detect.py          # PHÁT HIỆN trên dữ liệu THẬT B0329+54 (GREENBURST/GBT)
python psr_pipeline.py        # pipeline trên dữ liệu tổng hợp (~40 s)
python record_unattended.py --selftest   # test trình ghi tự động (không cần SDR)
python psr_targets.py         # bảng SNR dự đoán cho 10 pulsar × 5 cấu hình
```

Phụ:
```bash
python psr_targets.py --derived   # B, tuổi, Ė, khoảng cách DM của từng pulsar
python psr_targets.py --objects   # Cas A, Cyg A, M31, Mặt Trăng, ... (docs/04)
python psr_targets.py --transit   # giờ transit + thời gian HIỆU DỤNG khi để chảo cố định (docs/05 §8c)
python psr_targets.py --daytime   # pulsar nào quan sát được BAN NGÀY hôm nay (docs/05 §8b)
                                 # thêm --date 2027-02-15 --min-sep 45 để lên lịch
python psr_sensitivity.py --check # đối chiếu SEFD với PROJECT_PLAN.md
```

Yêu cầu: Python 3.10+, `numpy`, `matplotlib` (chỉ để vẽ). Không cần internet,
không cần SDR.

---

## 2. Năm con số phải nhớ

| Đại lượng | Giá trị | Ý nghĩa |
|---|---|---|
| `A_eff` | **5.91 m²** | chảo 3.7 m, η = 0.55 → đây là giới hạn cứng |
| `G` | **2.14 mK/Jy** | 1 Jy chỉ làm ăng-ten nóng thêm 2 mK |
| `SEFD` | **70 kJy** (T_sys 150 K) | độ nhạy; Cas A = 5.8 K, pulsar 25 mJy = 0.054 mK |
| `1σ` (2.4 MHz, 1 h) | **0.75 Jy** | thiết bị hiện có |
| Cách nhanh nhất | **dùng back-end 50 MHz có sẵn của kính (L-band)** — không mua gì | Vela: SNR 8 trong **~3 phút** |

**Kết luận trung tâm (cập nhật 2026-11 sau khi đối chiếu ATNF psrcat v2.9.0 và datasheet
RTP37)**: hệ kính **đã có** L-band + back-end 50 MHz + tracking 0,01°, nên bài lab
pulsar **không cần mua thêm gì**:

| Mục tiêu | Cách làm | Thời gian đạt SNR 8 |
|---|---|---|
| **Vela (B0833-45)** | L-band 50 MHz, track | **~3 phút** |
| **B0329+54** | L-band 50 MHz, track | **~25 phút** |
| **B1641-45** | L-band 50 MHz, track | **~22 phút** |
| B0950+08 | L-band (hoặc 423 MHz nếu mở rộng) | ~6,5 h (hoặc ~40 phút @423) |

⚠ **Đính chính flux**: bảng cũ dùng S400/S1400 chép tay, sai tới ×7 (B0329+54 ghi
200 mJy thay vì 1500; Vela 700 thay vì 5000) → "chỉ B0950+08 làm được" là **sai**.
Chi tiết: `docs/02` §4.0 (đính chính), §4.4 (hệ RTP37), §4.5 (dự phòng thiết bị).

---

## 3. Ba đính chính so với `PROJECT_PLAN.md`

1. **SEFD**: `250 Jy` → **70 040 Jy** (Tsys 150 K). Số cũ ứng với `A_eff = 1657 m²`,
   tức gấp 154 lần diện tích hình học của chảo — lỗi đơn vị. Mọi SNR pulsar trong
   `PROJECT_PLAN.md` vì thế bị ước lượng cao **~170–280 lần**.
2. **"B0329+54, RTL-SDR 2 MHz, 30 phút → SNR ≈ 30"**: giá trị đúng **≈ 0.18**.
3. **Thông lượng trong §3.1**: "Cua 0.5 Jy @1.4 GHz" thực tế là bậc của **tinh vân**
   Cua, pulsar chỉ ~10–20 mJy; "Vela 0.4 Jy" cao hơn thực tế ~3–4 lần.

→ Toàn bộ phần lập kế hoạch pulsar trong `PROJECT_PLAN.md` được **thay thế** bởi
`docs/02` (ngân sách S/N) và `docs/05` (kế hoạch). Phần HI **không** bị ảnh hưởng
(dòng HI mạnh gấp ~10⁴ lần pulsar).

---

## 4. Trạng thái: cái gì đã kiểm chứng, cái gì chưa

| Hạng mục | Trạng thái |
|---|---|
| Công thức vật lý (SEFD, beam, trễ DM, trải tán sắc) | ✅ `selftest.py` 22/22 |
| Khử tán sắc (A2), fold + SNR (cửa sổ vòng), tinh chỉnh P | ✅ |
| DM dải con (A11b/A11c, trọng số SNR + sigma-clip) | ✅ sai 0.2–1.2 % |
| zero-DM phân biệt RFI phẳng vs xung tán sắc | ✅ test riêng |
| Đọc/ghi `.fil` + kiểm chứng round-trip | ✅ |
| **Phát hiện trên DỮ LIỆU THẬT** (GREENBURST/GBT B0329+54) | ✅ 3 xung cùng pha, DM 25.98 vs 26.764, 5/5 kiểm chứng PASS |
| **Giao diện: mọi nút + đường dẫn** | ✅ `gui_verify.py` 37/37 PASS (đã bắt và sửa 6 lỗi thật) |
| **EXE đóng gói** | ✅ `PulsarObs.exe --selfcheck` 7 phép kiểm bên trong, `frozen=True` |
| **NGHIỆM THU đa điều kiện** | ✅ `acceptance_test.py` **61/61 ĐẠT** (S1 đầu vào · S2 fallback · S3 đầu ra · S4 GUI · S5 đối chiếu) |
| Trình ghi tự động (mock + đọc lại + gap log) | ✅ `--selftest` PASS |
| Trình ghi tự động trên **RTL-SDR thật** | ⚠ code sẵn, cần cắm thiết bị |
| Khử tán sắc kết hợp (A3) | ⚠ có hàm, cần stream liên tục |
| Quan sát trên kính RTP-3.7 | ❌ chờ giai đoạn 0–3 (`docs/05`) |

### Kết quả trên dữ liệu THẬT (`results/B0329+54_*`)

| Đại lượng | Đo được | Tham chiếu ATNF |
|---|---|---|
| 3 xung cùng pha (mod P) | 293.7 ± 0.6 ms | "three pulses" (mô tả bộ dữ liệu) |
| DM (trễ dải con) | 25.98 ± 0.50 | 26.7641 |
| DM (quét fold) | 27.25 (đỉnh 608σ) | 26.7641 |
| SNR xung mạnh nhất / bề rộng | 608 / 8.2 ms | W50 ≈ 6–12 ms |
| Đối chứng nền (xáo trộn kênh) | 9.2σ < 12 | ✅ không phát hiện giả |

---

## 5. Cảnh báo kỹ thuật (đọc trước khi tự viết lại)

Rút ra từ chính các lỗi đã mắc trong quá trình xây pipeline:

1. **Cửa sổ lọc khớp phải là VÒNG** — xung nằm ở pha 0 sẽ bị chia đôi, SNR tụt 2×.
2. **`nbin ≥ 4·P/W50`** — nếu không, SNR bị lượng tử hoá theo pha và đường cong DM
   xuất hiện "đỉnh giả" (đã gặp: DM đo 155 thay vì 200).
3. **FFT không đủ mịn để fold** — độ phân giải `1/T` làm pha trôi 0.4 % chu kỳ; phải
   tinh chỉnh chu kỳ (A4b).
4. **Xếp hạng FFT không đáng tin** — trong lần chạy mẫu, ứng viên hạng 1 là **nhiễu**
   (`2.5·f0`), f0 thật ở hạng 3; phải kiểm chứng bằng fold.
5. **Lọc khớp quét vị trí cho SNR ≈ 3.5 trên dữ liệu chỉ có nhiễu** → ngưỡng phát hiện
   phải là **SNR ≥ 6–8**, và phải xác nhận lại ở đêm khác, đúng pha.
6. **Cắt kênh hỏng phải làm trên dữ liệu THÔ**, không phải sau khi chuẩn hoá bandpass
   (chuẩn hoá sẽ xoá mất dấu hiệu).

---

## 6. Vận hành & việc tiếp theo

**Ngôn ngữ**: GUI có ô *Ngôn ngữ / Language* (Tiếng Việt ↔ English), lưu ở `settings.json`; hoặc chạy `--lang en`. Cần khởi động lại để áp dụng toàn bộ.

**Nơi lưu**: chọn được trên GUI (ô *Nơi lưu dữ liệu*) — lưu vào `settings.json`; kết quả vào `results/<ngày>_<giờ>/`.

**Ghi tự động 4–5 giờ không canh chừng** (xem `docs/06` §6):

```bash
python record_unattended.py --target B0950+08 --hours 4.5 --band 423
python psr_detect.py --file data/<ngày>/B0950p08_<stamp>.fil --dm-ref 2.97 --p 0.253065
```

**Phần cứng tối giản** (xem `docs/06` §1): chỉ bắt buộc feed + LNA + SDR;
BPF 380–450 MHz là món **duy nhất nên mua** (chống bão hoà ADC — phần mềm
không thay được); GPSDO/motor/nguồn chuẩn đều bù bằng `psr_swcomp.py`.

Việc tiếp theo: đo `T_sys` bằng Y-factor trên Cas A, khảo sát RFI 24 h,
xin báo giá SDR 10–20 MHz, chạy 4–8 đêm B0950+08 rồi `stack_profiles()`.
