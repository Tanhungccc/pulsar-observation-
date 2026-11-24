# Trạng thái hiện tại (bộ nhớ làm việc)

*Cập nhật: 2026-11-25. Ghi lại mỗi khi kết thúc một phiên làm việc.*

## Đã xong
- Vault này được dựng mới (không liên kết `AstroStack`).
- Bản vá nhãn/ký hiệu hình đã có trong code:
  - Bỏ nhãn `công suất dư`, thay bằng `cường độ tương đối (đã trừ nền, chuẩn hoá)`.
  - Bỏ badge `DỮ LIỆU THẬT` cố định; badge chỉ hiện khi có provenance đã xác minh (`data_state`).
  - Không còn chú thích SNR dạng `e+12`; SNR hiển thị có đơn vị `σ` và giới hạn trong khung.
  - Chú giải ★ ghi rõ tiêu chí "SNR lọc khớp cao nhất", không phải "đỉnh lớn nhất".
- `psr_render.py` vẽ lại panel phóng to trong GUI từ dữ liệu đã cache; `PANEL_ASPECT` giữ đúng tỉ lệ thiết kế của từng panel.
- `place_legend` giờ tính bán kính marker theo pixel: khoảng hở tâm điểm → chú giải ≥ nửa marker, chú giải zorder trên ★; `figure_report` kiểm cả mép marker (hết ★ đè chữ).
- Khung xem trong GUI khoá chiều cao theo tỉ lệ gốc của panel; nhánh raster dùng `aspect=equal` — hết kéo dãn méo khi đổi cỡ cửa sổ.
- Commit `382f85a` (2026-11-25): app thuần pulsar + khung xem đúng tỉ lệ + chú giải né marker.
- Tab 2 (2026-11-25): nút A–D tự chuyển sang `fig2_detection.png` của lần chạy đang chọn; crop theo `fig2_detection_panels.json` (bbox đo thật, ghi kèm mỗi lần chạy) hoặc khung gọt lề suptitle cho chạy cũ; fig1_overview xem nguyên khung; reset về panel A khi đổi hình/bắt đầu chạy mới; nền canvas theo theme tối.
- `selftest.py`: 37/37 PASS. `module_audit.py`: 149/149 PASS (2026-11-24).
- Ghi chú khoa học đã đối chiếu với `docs/03` và `docs/04` và sửa lại: vị trí chảo ±2° (nửa beam), Ṗ cần GPSDO, khoảng cách DM ±50 %, Mặt Trời chỉ drift scan, không trỏ quá 60 s.

## Phạm vi
- App này **chỉ về pulsar**. Đã bỏ: `docs/04` (quan sát khác), bảng nguồn continuum (`psr_targets.py --objects`), nút GUI "Nguồn continuum khác".
- `psr_rtcs.py`: GIỮ làm công cụ hiệu chuẩn T_sys/SEFD cho ngân sách S/N (quyết định của người dùng).
- Nhánh `hi_continuum` trong `ingest_guard.py`: ĐÃ BỎ. Guard giờ TỪ CHỐI phổ 1D (`SPECTRUM_1D`) và Δt > 10 ms (`TOO_SLOW`) kèm lý do — không định tuyến nhánh khác.

## Đang dở
- `results/`: đã xoá 877 file SVG/PNG/PDF nhãn sai, 11 PNG mồ côi và các thư mục chạy test trong phiên. Còn lại 299 SVG không có nhãn cũ + một số báo cáo audit cũ (`acceptance_report.txt`, `stress_matrix.json`, `stress_report.txt`) và `_gio_test_data` (trước phiên — chưa đụng).
- Bảng DM trong [[B0329+54 — mẫu kiểm chứng]] (27.25) chưa khớp với kết quả chạy mới (26.32) — cần đối lại.
- Nguyên nhân SNR `e+12` trong các hình cũ chưa truy tận gốc trong code hiện tại (không còn chuỗi sống nào).

## Việc kế tiếp
1. Quyết định số phận 299 SVG còn lại (chạy lại hay lưu trữ).
2. Vault đã đưa vào git (bỏ `.obsidian/`).
3. Khi có dữ liệu thật có header đáng tin, cập nhật provenance cho [[B0329+54 — mẫu kiểm chứng]].
4. Sửa toạ độ RTCS trong `configs/rtp37-hcmc.json` về 106.7009°E / 10.7769°N theo [[RTP-3.7 POAM]].
5. Xem lại 299 SVG + kiểm `fig1` bằng mắt trên một chạy mới (temp folder).

## Rủi ro đã biết
- Header file `B0329+54.fil` ghi `source=TEMP`: provenance chưa xác minh.
- Panel (d): điểm tần thấp 1019.9 MHz lệch ~7 ms, nguyên nhân chưa xác định.
- Toạ độ trạm đang nhập trong RTCS có thể lệch (xem [[RTP-3.7 POAM]]).
