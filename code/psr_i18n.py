# -*- coding: utf-8 -*-
"""psr_i18n.py — ĐA NGÔN NGỮ (Tiếng Việt / English) cho phần giao diện.

Cách dùng:
    import psr_i18n as L
    ttk.Button(..., text=L.t("▶ Bắt đầu ghi"))
    root.title(L.t("Pulsar Observation — POAM RTP-3.7 (TP.HCM)"))

Chuỗi nào chưa có bản dịch thì **giữ nguyên tiếng Việt** (không bao giờ hiện
khoá thô hay chuỗi rỗng).

Ngôn ngữ lưu ở `settings.json` (khoá "lang"), đọc theo thứ tự:
    biến môi trường PSR_LANG  >  settings.json  >  "vi"
"""
from __future__ import annotations

import os

LANGS = ("vi", "en")
LANG_NAMES = {"vi": "Tiếng Việt", "en": "English"}

# Bảng dịch: khoá là CHUỖI TIẾNG VIỆT đúng như trong giao diện.
VI2EN = {
    'Preview panel đã chọn.': 'Selected panel preview.',
    'Preview PNG panel đã chọn.': 'Selected panel PNG preview.',
    'Chọn panel A/B/C/D để xem.': 'Choose panel A/B/C/D to preview.',
    'Băng dự phòng SDR:': 'Fallback SDR band:',
    'Mục đích chuỗi dự phòng:': 'Fallback chain goal:',
    'Phát hiện chuỗi dự phòng': 'Detect fallback chain',
    'Hồ sơ thiết bị POAM': 'POAM hardware profile',
    'Mở toàn hình bằng trình xem ảnh': 'Open full figure in image viewer',
    'Mở toàn hình': 'Open full figure',
    'SVG (zoom ∞)': 'SVG (infinite zoom)',
    'Xem lớn…': 'Large view…',
    'Dùng SVG hoặc Xem lớn… để đọc chi tiết.': 'Use SVG or Large view… to inspect details.',
    'Toolbar Matplotlib: Home / Pan / Zoom khung. Mở cửa sổ lớn để xem rõ.': 'Matplotlib toolbar: Home / Pan / box Zoom. Open the large viewer for clarity.',
    'Chọn panel hoặc Xem lớn… để thao tác Home / Pan / Zoom khung.': 'Choose a panel or Large view… for Home / Pan / box Zoom.',
    'Chạy lại phát hiện để mở hình tương tác.': 'Run detection again to open an interactive figure.',
    'Xem biểu đồ — phóng to': 'View plot — enlarged',
    '⤢ Phóng to hình': '⤢ Maximise figure',
    '⤡ Thu lại': '⤡ Restore panels',
    'Hình phóng to — bám ⤡ Thu lại để xem bảng thông tin': 'Figure maximised — press ⤡ Restore panels to see the info blocks',
    'Đã hiện lại các khối thông tin': 'Info blocks restored',
    '↺ Về ban đầu': '↺ Reset view',
    'phóng 1,0× (toàn khung)': 'zoom 1.0× (full view)',
    'phóng': 'zoom',
    ' — ↺ để về toàn khung': ' — ↺ to reset',
    'Đã về khung ban đầu của panel đang xem': 'Reset the view of the current panel',
    'Xem:': 'View:',
    'Cả 4 panel': 'All 4 panels',
    'Chuỗi thời gian': 'Time series',
    'Quét DM': 'DM sweep',
    'Cận cảnh xung': 'Pulse close-up',
    'Trễ dải con': 'Subband lags',
    'Vẽ lại bằng VECTOR: lăn chuột = zoom SẮC tại con trỏ · kéo = di chuyển · nháy đúp/R = về ban đầu · 2 thanh trượt = cuộn/giãn cửa sổ': 'Rendered as VECTOR: scroll = crisp zoom at cursor · drag = pan · double-click/R = reset · sliders = pan/stretch the window',
    'Đang xem PNG của lần chạy trước (raster): zoom sẽ MỜ. Bấm Chạy phát hiện để vẽ lại bằng vector, hoặc mở SVG (zoom ∞)': 'Viewing a PNG from an earlier run (raster): zoom will be BLURRY. Run detection again for a vector redraw, or open SVG (infinite zoom)',
    "Vị trí cửa sổ": "Window position",
    "Độ rộng": "Width",
    "Lăn chuột: zoom · Kéo: di chuyển · Nháy đúp/R: về ban đầu · Muốn zoom nét vô hạn: mở SVG": "Scroll: zoom · Drag: pan · Double-click/R: reset · For infinite crisp zoom: open SVG",
    "Mở SVG (zoom ∞)": "Open SVG (infinite zoom)",
    "Chưa có bản vector": "No vector file yet",
    "Chưa có hình": "No figure yet",
    "Hãy chạy phát hiện trước.": "Run detection first.",
    "Hình này chỉ có PNG (lần chạy cũ). Hãy bấm Chạy phát hiện lại "
    "để có kèm .svg.": "This figure only has PNG (older run). "
    "Run detection again to get .svg.",
    'Sẵn sàng. Chọn tab để bắt đầu.': 'Ready. Pick a tab to start.',
    'Yêu cầu DỪNG — chờ file đóng an toàn…': 'STOP requested — waiting for a safe close…',
    'Xoá mục tiêu': 'Delete target',
    'Đang có tác vụ chạy — đợi hoàn tất trước.': 'A task is running — wait for it to finish.',
    'Thiếu mục tiêu': 'Missing target',
    'Hãy nhập tên mục tiêu.': 'Please enter a target name.',
    'Không có SDR': 'No SDR',
    'Chưa có file .fil nào trong data/ — hãy ghi thử trước.': 'No .fil yet in data/ — record a test session first.',
    'Chưa có file vừa ghi để phân tích.': 'No freshly recorded file to analyse.',
    'Lỗi': 'Error',
    'Chưa chọn file .fil hợp lệ': 'No valid .fil selected',
    "· RA có dấu ':' được hiểu là GIỜ-PHÚT-GIÂY; chỉ nhập số thì là ĐỘ.": "· RA with ':' is read as HOURS-MINUTES-SECONDS; a bare number is DEGREES.",
    'Không đổi được thư mục': 'Cannot change the folder',
    'Giờ/kênh/tsamp phải là số': 'hours/channels/tsamp must be numbers',
    'DM/P phải là số': 'DM/P must be numbers',
    '✔ Tác vụ hoàn tất.': '✔ Task finished.',
    '  1 · KẾ HOẠCH & GHI  ': '  1 · PLAN & RECORD  ',
    '  3 · CÀI ĐẶT & CÔNG CỤ  ': '  3 · SETTINGS & TOOLS  ',
    '  Danh mục & công cụ  ': '  Catalogue & tools  ',
    '  Hồ sơ trạm/kính  ': '  Site / telescope  ',
    '  Kiểm chứng  ': '  Verification  ',
    '  Nơi lưu & ngôn ngữ  ': '  Storage & language  ',
    '  Phần cứng  ': '  Hardware  ',
    'Băng (MHz)': 'Band (MHz)',
    'Chi tiết ▾': 'Details ▾',
    'Thu gọn ▴': 'Collapse ▴',
    'Chọn dữ liệu': 'Select data',
    'Cấu hình': 'Configuration',
    'DM tham chiếu': 'Reference DM',
    'Kiểm tra đầu vào': 'Input checks',
    'M3 — dò chu kỳ mù (FFT + sàng hài)': 'M3 — blind period search (FFT + harmonics)',
    'Mở hình fig3': 'Open fig3',
    'Mở thư mục kết quả': 'Open results folder',
    'Ngưỡng gatekeeper (ingest_guard)': 'Gatekeeper thresholds (ingest_guard)',
    'Phân tích': 'Analysis',
    'Thời lượng (giờ)': 'Duration (h)',
    'Trạm & kính (hồ sơ)': 'Site & telescope (profile)',
    'bình thường': 'nominal',
    'chưa chạy (cần P tham chiếu hoặc --search-period)': 'not run (needs reference P or --search-period)',
    'chưa chạy — bấm Chạy phát hiện': 'not run — press Run detection',
    'chưa có dữ liệu': 'no data yet',
    'dò chu kỳ mù (FFT) khi không có P': 'blind period search (FFT) when P is unknown',
    'ingest_guard — dữ liệu vào đã được nhận dạng thế nào': 'ingest_guard — how the input data was recognised',
    'không có ứng viên vượt ngưỡng': 'no candidate above threshold',
    'lỗi: ': 'error: ',
    'Đổi hồ sơ: đặt biến môi trường PSR_PROFILE=<file.json> hoặc sửa configs/. Không cần sửa code.': 'Switch profile: set PSR_PROFILE=<file.json> or edit configs/. No code change needed.',
    '→ Sang Tab 2': '→ Go to Tab 2',
    '▸ Nâng cao': '▸ Advanced',
    '▾ Nâng cao': '▾ Advanced',
    'Chạy phát hiện': 'Run detection',
    'Đang chạy…': 'Running…',
    'MỤC': 'SECTIONS',
    'MỤC TIÊU': 'TARGET',
    'NGUỒN DỮ LIỆU': 'DATA SOURCE',
    'Cấu hình & ghi': 'Configuration & recording',
    'Kế hoạch đêm nay': "Tonight's plan",
    'Nâng cao': 'Advanced',
    'Mở rộng ▾': 'Expand ▾',
    'Thu gọn ▴': 'Collapse ▴',
    'Nhật ký hoạt động': 'Activity log',
    'Dò lại': 'Probe again',
    '＋ Thêm…': '+ Add…',
    'Tối': 'Dark',
    'Sáng': 'Light',
    'Độ phóng giao diện:': 'UI scale:',
    'Áp dụng': 'Apply',
    'Kênh': 'Channels',
    'Mở thư mục': 'Open folder',
    'Hồ sơ:': 'Profile:',
    'Chu kỳ P (s):': 'Period P (s):',
    'Số kênh IQ:': 'IQ channels:',
    'Cách dùng': 'How to use',
    'Nhật ký': 'Log',
    'kênh {n} · {t} µs': 'channels {n} · {t} µs',
    'Giao diện: {m} — khởi động lại…': 'Theme: {m} — restarting…',
    'Ngôn ngữ: {x} — khởi động lại…': 'Language: {x} — restarting…',
    'Còn trống {f:.0f} GB · cần ~{n:.0f} GB cho 5 h': '{f:.0f} GB free · ~{n:.0f} GB needed for 5 h',
    # --- khung chung
    "Pulsar Observation — POAM RTP-3.7 (TP.HCM)": "Pulsar Observation — POAM RTP-3.7 (HCMC)",
    "Nhật ký": "Log",
    "Kết quả": "Results",
    # --- tab
    "  1 · GHI TỰ ĐỘNG  ": "  1 · RECORD  ",
    "  2 · PHÁT HIỆN  ": "  2 · DETECT  ",
    "  3 · MỤC TIÊU  ": "  3 · TARGETS  ",
    "  4 · PHẦN CỨNG  ": "  4 · HARDWARE  ",
    "  5 · KIỂM CHỨNG  ": "  5 · VERIFY  ",
    # --- tab 1
    "Ghi phổ động (dynamic spectrum) — 4–5 giờ, không cần canh chừng":
        "Dynamic-spectrum recording — 4–5 h, unattended",
    "Mục tiêu:": "Target:",
    "Băng (MHz):": "Band (MHz):",
    "Thời lượng (giờ):": "Duration (h):",
    "Kênh:": "Channels:",
    "tsamp (µs):": "tsamp (µs):",
    "Nguồn dữ liệu:": "Data source:",
    "Làm mới": "Refresh",
    "＋ Mục tiêu…": "+ Target…",
    "Nơi lưu dữ liệu (có thể chọn ổ khác, ví dụ SSD ngoài)":
        "Save locations (choose another drive, e.g. external SSD)",
    "Dữ liệu thô:": "Raw data:",
    "Kết quả:": "Results:",
    "Chọn…": "Browse…",
    "Mở": "Open",
    "Áp dụng": "Apply",
    "(ghi vào settings.json cạnh app; có hiệu lực ngay, không cần khởi động lại)":
        "(stored in settings.json next to the app; applied immediately, no restart)",
    "Ngôn ngữ / Language:": "Ngôn ngữ / Language:",
    "▶ Bắt đầu ghi": "▶ Start recording",
    "■ Dừng": "■ Stop",
    "Phân tích file vừa ghi": "Analyse the file just recorded",
    "Mở thư mục dữ liệu": "Open data folder",
    "Cách dùng": "How to use",
    "… đang dò thiết bị": "… probing hardware",
    # --- trạng thái phần cứng
    "🟡 Bắt buộc MÔ PHỎNG — dữ liệu không phải thu thật":
        "🟡 Forced MOCK — data is not a real observation",
    "🔴 KHÔNG có SDR — chế độ bắt buộc thật sẽ BÁO LỖI":
        "🔴 No SDR — strict real mode will ABORT",
    "🟡 Tự động → MÔ PHỎNG (không thấy SDR)":
        "🟡 Auto → MOCK (no SDR found)",
    "🟢": "🟢",
    "đã kết nối": "connected",
    # --- tab 2
    "Phát hiện pulsar trên file filterbank (.fil)":
        "Pulsar detection on filterbank / PSRFITS / raw IQ",
    "Chọn file .fil…": "Choose file…",
    "DM tham chiếu:": "Reference DM:",
    "IQ → kênh:": "IQ → channels:",
    "▶ Chạy phát hiện": "▶ Run detection",
    "Mở metrics JSON": "Open metrics JSON",
    "Mở báo cáo TXT": "Open TXT report",
    "Mở thư mục kết quả của lần chạy": "Open this run's result folder",
    "Mở bằng trình xem ảnh": "Open in image viewer",
    "Biểu đồ kết quả": "Result figures",
    "Hình:": "Figure:",
    # --- tab 3
    "Khả năng quan sát từ TP.HCM (lat 10.78°N)":
        "Observability from the site (lat 10.78°N)",
    "Ngày (YYYY-MM-DD, bỏ trống = hôm nay):": "Date (YYYY-MM-DD, empty = today):",
    "Băng thông (MHz):": "Bandwidth (MHz):",
    "Giờ transit (để chảo cố định)": "Transit time (fixed dish)",
    "Quan sát ban ngày": "Daytime observing",
    "Bảng SNR (mọi mục tiêu) × 5 cấu hình": "SNR table (all targets) × 5 configs",
    "Đại lượng suy ra (B, tuổi, Ė)": "Derived quantities (B, age, Ė)",
    "＋ Quản lý mục tiêu…": "+ Manage targets…",
    "Bảng kết quả": "Result table",
    # --- tab 4
    "Dự đoán chuỗi linh kiện + tự fallback":
        "Receiver-chain prediction + automatic fallback",
    "Mục đích:": "Goal:",
    "Băng:": "Band:",
    "Phát hiện chuỗi": "Detect chain",
    # --- tab 5
    "Kiểm chứng máy móc (chạy trước khi tin kết quả)":
        "Machine verification (run before trusting any result)",
    "▶ Chạy selftest nhanh (21 test)": "▶ Quick selftest (21 tests)",
    "Pipeline mô phỏng (nhanh)": "Simulated pipeline (fast)",
    "Tự kiểm tra công thức": "Formula self-check",
    "Tự kiểm tra trình ghi (mock)": "Recorder self-test (mock)",
    "▶ Corpus dữ liệu XẤU (data/stress)": "▶ Bad-data corpus (data/stress)",
    "Mở tài liệu docs": "Open docs folder",
    "Kết quả kiểm chứng": "Verification output",
    # --- hộp thoại
    "Mục tiêu — thêm/sửa (lưu vào targets_user.json)":
        "Target — add/edit (saved to targets_user.json)",
    "Lưu": "Save",
    "Xoá mục tiêu": "Delete target",
    "Đóng": "Close",
    "Sửa giúp: ": "Please fix: ",
    "Không có SDR": "No SDR",
    "Không thấy SDR — sẽ ghi MÔ PHỎNG": "No SDR found — will record MOCK data",
    "Thiếu mục tiêu": "Missing target",
    "Lỗi": "Error",
    "Không đổi được thư mục": "Cannot change folder",
    "Xoá mục tiêu": "Delete target",
    # --- thông báo dài (dùng trong hộp thoại)
    "Đang chọn 'Bắt buộc SDR THẬT' nhưng không tìm thấy thiết bị:":
        "Mode is 'Strict real SDR' but no device was found:",
    "Cắm lại thiết bị rồi bấm Làm mới, hoặc đổi sang 'Tự động'.":
        "Re-plug the device and press Refresh, or switch to 'Auto'.",
    "Không tìm thấy RTL-SDR:": "No RTL-SDR found:",
    "OK = ghi dữ liệu MÔ PHỎNG (để kiểm chứng chuỗi)":
        "OK = record MOCK data (to exercise the chain)",
    "Cancel = dừng lại để cắm thiết bị": "Cancel = stop and plug the device",
}

_cur = None


def _settings_get() -> str | None:
    try:
        import psr_paths
        return psr_paths.load_settings().get("lang")
    except Exception:                            # noqa: BLE001
        return None


def current() -> str:
    """Ngôn ngữ đang dùng: 'vi' hoặc 'en'."""
    global _cur
    if _cur in LANGS:
        return _cur
    env = (os.environ.get("PSR_LANG") or "").strip().lower()
    if env in LANGS:
        _cur = env
        return _cur
    st = _settings_get()
    _cur = st if st in LANGS else "vi"
    return _cur


def set_lang(lang: str, persist: bool = True) -> str:
    """Đổi ngôn ngữ; lưu vào settings.json để lần sau giữ nguyên."""
    global _cur
    lang = (lang or "vi").strip().lower()
    if lang not in LANGS:
        raise ValueError(f"ngôn ngữ không hỗ trợ: {lang}")
    _cur = lang
    if persist:
        try:
            import psr_paths
            d = psr_paths.load_settings()
            d["lang"] = lang
            psr_paths.save_settings(d)
        except Exception:                        # noqa: BLE001
            pass
    return lang


def t(text: str) -> str:
    """Dịch một chuỗi giao diện. Không có bản dịch → trả nguyên chuỗi gốc."""
    if not text:
        return text
    if current() == "en":
        return VI2EN.get(text, text)
    return text


def is_en() -> bool:
    return current() == "en"


def coverage() -> dict:
    """Thông tin phục vụ self-check: số chuỗi đã dịch."""
    return dict(lang=current(), langs=list(LANGS), n_translated=len(VI2EN))


def self_check() -> list:
    bad = []
    if current() not in LANGS:
        bad.append(f"ngôn ngữ không hợp lệ: {current()}")
    # dịch phải đổi được và trả lại được
    keep = current()
    try:
        set_lang("vi", persist=False)
        vi = t("▶ Bắt đầu ghi")
        set_lang("en", persist=False)
        en = t("▶ Bắt đầu ghi")
        if vi == en:
            bad.append("bản dịch EN trùng VI")
        if t("chuỗi không có trong bảng") != "chuỗi không có trong bảng":
            bad.append("fallback không giữ nguyên chuỗi gốc")
    finally:
        set_lang(keep, persist=False)
    return bad


if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                            # noqa: BLE001
        pass
    print("coverage:", coverage())
    print("self_check:", self_check() or "PASS (0 lỗi)")
    for s in ("▶ Bắt đầu ghi", "Nhật ký", "Kết quả"):
        print(f"  {s!r} → {t(s)!r}")
