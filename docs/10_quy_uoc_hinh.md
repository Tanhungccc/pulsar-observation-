# 10 — Quy ước ký hiệu, provenance và xem/zoom biểu đồ

## Quy ước đã đối chiếu với caption bài báo

| Dấu/nét | Nghĩa trong ứng dụng | Tham khảo |
|---|---|---|
| ● đặc | điểm đo | arXiv:1501.03312: “filled red circles” cho phép đo; caption đối chiếu “open squares” cho đại lượng khác |
| ○ rỗng | điểm residual được đánh dấu; **không tự hàm ý RFI** | Cùng caption dùng open squares cho component separation; residual chỉ là residual của model |
| Nét liền | đường fit | astro-ph/0701193 phân biệt GP “solid line” với AP “dotted line” |
| Nét đứt | tham chiếu | arXiv:2003.01071: “line of equal flux values … dashed line” |
| Dải tô | vùng bất định/sai số hệ thống | arXiv:2003.01071: systematic error được biểu diễn bằng vùng tô quanh đường tham chiếu |
| Error bar | sai số đo | Cùng bài mô tả error bar |
| ★ | candidate có matched-filter SNR cao nhất; không đồng nghĩa peak-amplitude cao nhất | arXiv:2606.10807 dùng star cho brightest observed pulse; ứng dụng legend ghi tiêu chí matched-filter SNR |
| ▲/▼ | hướng biến thiên | arXiv:1511.01767 dùng triangles cho DM tăng/giảm; không dùng tam giác để chỉ vị trí đỉnh |

### Diễn giải đúng các panel B0329+54

- Panel (a): pulse 1722.9 ms có matched-filter SNR 608.35, peak chuẩn hoá ≈0.703;
  pulse 291.6 ms có peak ≈0.768 nhưng SNR 593.42. Vì vậy ★ chỉ highlight candidate
  có SNR lọc khớp cao nhất; legend proxy ghi tiêu chí. Preview ngang/thấp đặt legend
  upper-center, kiểm tra bbox marker/legend không overlap.
- Panel (d): 8 subband, DM Theil–Sen ≈26.32 pc cm⁻³; leave-one-subband-out
  jackknife ≈0.79 pc cm⁻³ (kèm sàn hệ thống 3%), giữ đủ 8 điểm. Điểm thấp tần
  1019.9 MHz có residual khoảng −7.1 ms so với đường fit; nguyên nhân chưa xác định.
  Không báo “17σ”: với chỉ 8 subband, không diễn giải residual thành pointwise
  Gaussian significance. Đây là fit kiểm tra, không phải hiệu chuẩn độc lập.
- “DM boxcar” ở panel (b) và “DM subband” ở (d) là phép đo khác nhau. Giữ cả hai,
  kèm phương pháp và sai số; không ép chúng thành một số duy nhất.
- Trục thời gian: **cường độ tương đối (đã trừ nền, chuẩn hoá)**. Đây không phải
  residual của một mô hình vật lý fit.
- Provenance: không đóng badge/tiêu đề “DỮ LIỆU THẬT” chỉ vì file đọc được. Header
  `TEMP/TEST` được đánh dấu chưa xác minh; source provenance cần metadata đáng tin.

## Định dạng và xem hình

Mỗi hình lưu **PNG** để preview và **SVG** cho quy trình báo cáo bên ngoài. Không xuất
PDF hoặc HTML. Trong Tab 2 preview một panel A/B/C/D, không có zoom/pan tích hợp.
Nút **Mở toàn hình bằng trình xem ảnh** mở PNG gốc bằng ứng dụng ngoài.

## Kiểm chứng tự động

`module_audit.py` kiểm tra SVG/PNG, trục/legend và marker ★ không đè legend ở preview
rộng/thấp; residual không bị gán nguyên nhân; provenance không tự mặc định là thật.
`figure_check` kiểm tra legend/nhãn/trục trên hình kết quả.
