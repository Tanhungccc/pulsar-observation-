# Pulsar Observation Brain — POAM RTP-3.7

Bộ não của dự án: mọi agent đọc trang này trước. Vault này **hoàn toàn độc lập** với vault `AstroStack` (không liên kết, không chỉnh sửa).

## Đọc theo thứ tự
1. [[Quy tắc cho Agent]] — ràng buộc bắt buộc khi làm việc trong repo.
2. [[Trạng thái hiện tại]] — việc đang dở, số liệu đã xác minh, việc kế tiếp.
3. [[Sơ đồ luồng.canvas|Sơ đồ luồng]] — từ thiết bị → thu → detect → báo cáo.

## Thiết bị
- [[RTP-3.7 POAM]] — chảo 3.7 m, receiver, LNA/feed, ràng buộc phần cứng.

## Pipeline & code
- [[Pipeline phát hiện pulsar]] — `psr_detect.py` và các module phụ trợ.
- [[Quy ước hình vẽ]] — ký hiệu, nhãn provenance, quy tắc SNR.

## Khoa học
- [[Pulsar có thể đo gì]] — tọa độ, DM, chu kỳ, W50, đặc điểm.
- [[B0329+54 — mẫu kiểm chứng]] — số liệu chạy thật gần nhất.

## Nguồn tài liệu gốc (trong repo, không sao chép)
- `docs/01…08` — vật lý, chuỗi thu, kế hoạch 5 giai đoạn (`05_ke_hoach_trien_khai.md`).
- `docs/09_ho_so_thiet_bi_rtp37.md` — nguồn duy nhất về phần cứng (có nhãn `[DS]/[ẢNH]/[ĐO]/[TÍNH]/[?]`).
- `docs/10_quy_uoc_hinh.md` — quy ước ký hiệu hình.
- `radio research/` (ngoài repo) — manual, dữ liệu RTCS, script tính toán.
