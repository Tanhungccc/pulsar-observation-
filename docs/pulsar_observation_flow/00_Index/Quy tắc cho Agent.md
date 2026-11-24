# Quy tắc cho Agent

## Ranh giới tuyệt đối
- **Không đọc, không ghi, không liên kết** vault/thư mục `D:/tapcode/AstroStack/docs/astrostackflow`. Đây là vault khác, không thuộc dự án này.
- `data/` là **chỉ đọc**. Không ghi, không sửa, không xoá file thô (`.fil`, `.json` metadata).
- Kết quả chỉ ghi vào `results/<timestamp>/` (mỗi lần chạy một thư mục con). Không rải file ra gốc `results/`.
- Không xoá `results/` cũ tự động. Chỉ liệt kê và đề nghị người dùng quyết định.

## Đúng số liệu trước khi nói
- Mọi con số phải có nguồn: `detect_metrics.json`, `detect_report.txt`, hoặc tài liệu trong `docs/` có nhãn `[DS]/[ẢNH]/[ĐO]/[TÍNH]/[?]`.
- Không tự suy ra nguyên nhân vật lý (RFI, pulse shape, edge loss) chỉ từ residual. Ghi "chưa xác định".
- Không gọi residual 8 subband là "N sigma". Không báo "17σ".
- Không gắn nhãn "DỮ LIỆU THẬT" chỉ vì file đọc được. Header `TEMP`/`TEST` → provenance là **chưa xác minh**.
- Phân biệt rõ: DM boxcar (`dm_best`) ≠ DM subband (Theil–Sen). Giữ cả hai, kèm sai số.

## Khi sửa code
- Trước khi sửa: `git status` và đọc diff hiện có. Repo đang có nhiều thay đổi chưa commit, không được revert phần của người khác.
- Sau khi sửa: `python -m py_compile` các file đã sửa; chạy `code/module_audit.py` hoặc `code/selftest.py` khi thay đổi hình/pipeline.
- Kiểm tra hình bằng cách đọc PNG thật, không chỉ đọc log.
- Mọi hàm vẽ dùng `psr_plots.py`. Không hard-code chuỗi nhãn tiếng Việt mới ngoài `psr_i18n.py` nếu có khả năng hiển thị ở GUI.

## Ngôn ngữ và định dạng
- Chữ trong hình và báo cáo: tiếng Việt UTF-8, dấu thập phân là dấu chấm.
- Ghi chú trong vault: tiếng Việt, thuật ngữ kỹ thuật giữ nguyên tiếng Anh (DM, SNR, W50, subband).

## Trước khi kết thúc một phiên
- Cập nhật [[Trạng thái hiện tại]]: việc đã xong, việc dở, file đã đổi.
- Xoá file tạm của chính mình (ví dụ trong `%TEMP%`). Không xoá thứ người dùng tạo.
