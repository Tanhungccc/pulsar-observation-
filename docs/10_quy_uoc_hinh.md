# 10 — Quy ước vẽ hình & định dạng tệp (có trích dẫn)

Tài liệu này chốt **mọi ký hiệu/định dạng hình** của app. Nguyên tắc: **không tự
đặt ra quy ước** — mỗi ký hiệu phải có tiền lệ trong bài báo hoặc tài liệu kỹ
thuật, và ghi rõ nguồn. Mã nguồn tương ứng: `code/psr_plots.py` (đầu tệp).

## 1. Bảng quy ước ký hiệu

| Ký hiệu | Nghĩa trong app | Nguồn (trích nguyên văn caption) |
|---|---|---|
| **●** (chấm đặc) | điểm **ĐO được** | arXiv:1501.03312 — *"based on pulse broadening (filled red circles) and component separation (open squares)"* |
| **○** (chấm rỗng) | điểm **lệch khớp / đại lượng suy ra** | cùng nguồn: *"open squares"* dùng cho đại lượng suy ra; ở đây ○ đánh dấu điểm lệch khớp > 3σ |
| **—** (nét liền) | **đường mô hình khớp** dữ liệu của chính mình | astro-ph/0701193 — *"An example of a GP (solid line) in comparison with an AP (dotted line)"*: nét liền = sản phẩm chính |
| **--** (nét đứt) | **giá trị tham chiếu ngoài** (DM catalogue, đường bằng nhau) | arXiv:2003.01071 — *"The line of equal flux values is shown by a green dashed line"* |
| **dải tô** | **bất định / sai số hệ thống** | cùng bài — *"The systematic error … is represented by the green surface around the diagonal dashed line"* |
| **thanh sai số** | bất định **từng điểm đo** | cùng bài — *"with an error bar of 50 %"* |
| **★** | **giá trị sáng nhất / cực trị** | arXiv:2606.10807 — *"for the average flux density (plus symbol) and for the brightest observed pulse (stars)"* |
| **▲ / ▼** | **chiều biến thiên / loại trạng thái** — *không* dùng để trỏ đỉnh | arXiv:1511.01767 — *"upward/downward triangles indicate DM values increasing/decreasing with time. Unfilled triangles mark pulsars without significant DM variation"* |

### Hệ quả đã áp dụng trong code

1. **Bỏ hẳn ▼ "trỏ đỉnh xung"** ở panel (a) và (c): không có tiền lệ; tam giác
   trong bài báo mang nghĩa *chiều biến thiên*, dùng lại sẽ sai nghĩa.
2. **Chỉ đánh dấu MỘT xung — xung sáng nhất — bằng ★** (tiền lệ "brightest
   observed pulse (stars)"). Các xung còn lại được **liệt kê bằng chữ** trong
   chú giải (`+2 xung khác: 292, 1006 ms`), đúng cách bài báo xử lý (bảng hoặc
   chú giải), không rải ký hiệu khắp hình.
3. **Bỏ nét đứt đỏ dọc mỗi xung** (panel a trước đây): nét đứt đã dành riêng cho
   giá trị tham chiếu, dùng hai nghĩa trên cùng một hình là sai quy ước.
4. **Đường SNR theo DM** vẽ **nét liền không marker**: ~1 000 bước DM san sát,
   marker sẽ đè khít thành dải đậm và che vùng đỉnh.
5. **Panel dải con**: ● đo được + nét khớp + **dải ±1σ** + **thanh sai số từng
   điểm** + **○ cho điểm lệch khớp > 3σ** (ghi rõ số σ trong chú giải). Nhờ vậy
   điểm nhiễu tần số thấp lệch 17σ được nêu ra thay vì bị dải mờ che mất.

## 2. Định dạng tệp hình

| Tệp | Dùng khi nào | Vì sao |
|---|---|---|
| `figN_*.png` (200 dpi) | xem nhanh trong app, chèn báo cáo ngắn | nhẹ, hiển thị tức thì; **là raster → phóng to sẽ vỡ nét** |
| `figN_*.svg` | **soi chi tiết, zoom vô hạn** (Edge/Chrome/Inkscape) | vector thật, chữ là `<text>` (chọn/copy/dịch được), không cần cài gì thêm |
| `figN_*.pdf` | **KHÔNG dùng** | người dùng không chấp nhận định dạng PDF |
| `.html` (Plotly/Bokeh) | **KHÔNG dùng** | phải có trình duyệt/webview → phá ràng buộc "Tkinter thuần" |

Vì sao **SVG** mà không EPS/PS (hai định dạng vector khác của matplotlib):
EPS/PS dùng bảng mã cũ, **mất dấu tiếng Việt** ("tần số" → "t?n s?") và không
mở trực tiếp bằng trình duyệt. Danh sách định dạng hỗ trợ của matplotlib:
`png, pdf, ps, eps, svg, svgz, raw, rgba, jpg, tif, webp, pgf` — trong đó chỉ
`svg` thoả đồng thời: vector + Unicode + mở bằng công cụ có sẵn.

## 3. Tương tác trong app (không cần HTML)

`code/psr_zoom.py` gắn vào khung hình Tab 2 — cùng cảm giác với công cụ web
nhưng chạy trong Tkinter:

| Thao tác | Kết quả |
|---|---|
| Lăn chuột | zoom quanh vị trí con trỏ (trục X) |
| Shift + lăn chuột | zoom trục Y |
| Kéo chuột trái | di chuyển (pan) cả hai trục |
| Nháy đúp | trả về khung nhìn ban đầu |
| Thanh trượt **Vị trí / Độ rộng** | cuộn và giãn cửa sổ dữ liệu (như range-slider) |
| Phím ← → ↑ ↓ / + − / R | cuộn / zoom / reset |

Lưu ý trung thực: zoom trong app là phóng **ảnh đã vẽ** (raster trên canvas).
Muốn xem tới từng điểm dữ liệu thì mở **SVG** — vector nên không giới hạn độ nét.

## 4. Kiểm chứng tự động

- `module_audit.py` → nhóm `psr_plots (vector)` (đủ PNG+SVG, SVG hợp lệ, chữ là
  text, **không** sinh PDF/HTML) và nhóm `psr_zoom` (zoom 2× đúng, pan không đổi
  độ rộng, reset đúng khung gốc, `set_window` đúng vị trí/độ rộng).
- `figure_check` trong `psr_detect` chặn chú giải/chú thích đè dữ liệu hoặc tràn
  khung — đã bắt được chính chú thích mới thêm trong quá trình làm mục này.
