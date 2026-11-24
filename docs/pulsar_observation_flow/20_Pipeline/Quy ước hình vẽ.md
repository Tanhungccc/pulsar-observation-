# Quy ước hình vẽ

Nguồn đầy đủ: `docs/10_quy_uoc_hinh.md`. Ghi chú này là bản tóm tắt để tra nhanh.

| Ký hiệu / nhãn | Nghĩa |
|---|---|
| ● | điểm đo |
| ○ | residual được đánh dấu, **không** hàm ý RFI |
| nét liền | đường khớp |
| nét đứt | giá trị tham chiếu |
| dải tô | bất định / sai số hệ thống |
| ★ | ứng viên có SNR lọc khớp cao nhất (không phải đỉnh biên độ cao nhất) |
| ▲/▼ | chiều biến thiên DM (không dùng để chỉ đỉnh) |

## Quy tắc
- Trục cường độ: "cường độ tương đối (đã trừ nền, chuẩn hoá)". Không gọi là "công suất dư".
- SNR ghi kèm đơn vị `σ`. Không ghi số dạng `e+12`: đó là dấu hiệu lỗi độ lệch chuẩn nền.
- Không gắn badge "DỮ LIỆU THẬT" khi chưa xác minh provenance. Badge do `data_state` quyết định.
- Không ghi "17σ" hay residual "N sigma" với 8 subband.
- Chú giải và chú thích không được đè lên dữ liệu. Vị trí chú giải được đo bằng bbox sau khi vẽ.
