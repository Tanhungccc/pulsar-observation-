# Pipeline phát hiện pulsar

## Điểm vào
- `code/psr_detect.py`: `--file`, `--dm-ref`, `--p`, `--dm-max`, `--dm-step`, `--thresh` (mặc định 8σ), `--search-period`, `--top-n`.
- Đầu ra vào `results/<timestamp>/`: `fig1_overview`, `fig2_detection` (PNG + SVG), `detect_metrics.json`, `detect_report.txt`.

## Module liên quan
- `psr_fil.py`, `psr_fits.py`, `psr_iq.py`: đọc dữ liệu (filterbank, PSRFITS, IQ).
- `psr_core.py`: khử tán sắc, trễ DM.
- `psr_period.py`: tìm chu kỳ.
- `psr_plots.py`: mọi hàm vẽ, `finalize()` kiểm tra bố cục.
- `psr_render.py`: dựng lại 4 panel trong GUI từ dữ liệu đã cache.
- `psr_rtcs.py`: phân tích RTCS.
- `module_audit.py`, `selftest.py`: kiểm chứng tự động.

## Các bước
1. Đọc file, kiểm tra đầu vào (NaN, kênh nóng, RFI xung).
2. Veto zero-DM: đỉnh nằm ở DM≈0 thì nghi RFI nội địa.
3. Quét DM bằng boxcar đa độ rộng, hoặc fold tại P nếu có P.
4. Lọc ứng viên theo ngưỡng; kiểm tra nhất quán DM và pha (mod P).
5. Đo DM theo subband (Theil–Sen, jackknife) cho xung mạnh nhất.
6. Ghi hình, metrics, báo cáo.

## Bẫy đã biết
- Không có `psr_detect.analyze_folder`. Phân tích RTCS dùng `psr_rtcs.analyse_all(line, continuum, scan, out_dir)`.
- Console Windows: chạy với `PYTHONIOENCODING=utf-8` nếu in tiếng Việt, nếu không `--help` sẽ lỗi cp1252.
- Header `TEMP`/`TEST` → provenance "chưa xác minh" (xem [[Quy ước hình vẽ]]).

Liên quan: [[Trạng thái hiện tại]], [[B0329+54 — mẫu kiểm chứng]].
