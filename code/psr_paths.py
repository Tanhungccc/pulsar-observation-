# -*- coding: utf-8 -*-
"""psr_paths.py — CHÍNH SÁCH ĐƯỜNG DẪN (một nơi duy nhất).

Quy tắc I/O của toàn ứng dụng:

    <app>/data/      DỮ LIỆU THÔ — CHỈ ĐỌC. Không module nào được ghi vào đây,
                     trừ trình ghi (record_unattended) tạo file mới.
    <app>/results/   MỌI SẢN PHẨM: report.json, report.txt, hình, ứng viên.
                     Mỗi lần chạy → đúng MỘT thư mục con <tên dữ liệu>.
    <app>/configs/   Hồ sơ trạm/kính (JSON). Chỉ đọc khi chạy; người dùng sửa.
    <app>/tmp/       Tệp tạm của ứng dụng (tự dọn); mặc định dùng %TEMP% của OS.

Mọi module lấy đường dẫn từ đây — không tự tính `os.path.dirname(__file__)`.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile


def app_dir() -> str:
    """Thư mục ghi được của ứng dụng (cạnh .exe khi đóng gói)."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def settings_path() -> str:
    return os.environ.get("PSR_SETTINGS") or os.path.join(app_dir(), "settings.json")


def load_settings() -> dict:
    """Đọc settings.json (nơi lưu do người dùng chọn). Hỏng/thiếu → {}."""
    p = settings_path()
    try:
        with open(p, encoding="utf-8") as fh:
            d = json.load(fh)
        return d if isinstance(d, dict) else {}
    except Exception:                            # noqa: BLE001
        return {}


def save_settings(d: dict) -> str:
    """Ghi settings.json NGUYÊN TỬ (mất điện không cụt file)."""
    p = settings_path()
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(d, fh, ensure_ascii=False, indent=2)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, p)
    return p


def set_data_dir(path: str) -> str:
    """Đổi nơi GHI dữ liệu thô (phải ghi được). Trả về đường dẫn tuyệt đối."""
    p = os.path.abspath(path)
    os.makedirs(p, exist_ok=True)
    if not os.access(p, os.W_OK):
        raise PermissionError(f"không ghi được vào {p}")
    d = load_settings()
    d["data_dir"] = p
    save_settings(d)
    return p


def set_results_dir(path: str) -> str:
    """Đổi nơi GHI sản phẩm phân tích."""
    p = os.path.abspath(path)
    os.makedirs(p, exist_ok=True)
    if not os.access(p, os.W_OK):
        raise PermissionError(f"không ghi được vào {p}")
    d = load_settings()
    d["results_dir"] = p
    save_settings(d)
    return p


def data_dir() -> str:
    """Dữ liệu thô — CHỈ ĐỌC (trình ghi tạo file mới ở đây).

    Ưu tiên: PSR_DATA_DIR (env) > settings.json > <app>/data
    """
    return (os.environ.get("PSR_DATA_DIR")
            or load_settings().get("data_dir")
            or os.path.join(app_dir(), "data"))


def results_dir() -> str:
    """Mọi sản phẩm phân tích.

    Ưu tiên: PSR_RESULTS_DIR (env) > settings.json > <app>/results
    """
    return (os.environ.get("PSR_RESULTS_DIR")
            or load_settings().get("results_dir")
            or os.path.join(app_dir(), "results"))


def config_dir() -> str:
    """Hồ sơ trạm/kính."""
    return os.environ.get("PSR_PROFILE_DIR") or os.path.join(app_dir(), "configs")


def temp_dir() -> str:
    """Thư mục tạm (không nằm trong data/ hay results/)."""
    base = os.environ.get("PSR_TEMP_DIR")
    if base:
        os.makedirs(base, exist_ok=True)
        return base
    return tempfile.gettempdir()


def ensure_dirs() -> dict:
    """Tạo sẵn data/, results/, configs/ nếu thiếu (idempotent)."""
    out = {}
    for name, p in (("data", data_dir()), ("results", results_dir()),
                    ("configs", config_dir())):
        try:
            os.makedirs(p, exist_ok=True)
            out[name] = p
        except Exception as exc:                 # noqa: BLE001
            out[name] = f"LỖI: {exc!r}"
    return out


def output_dir(stem: str) -> str:
    """Thư mục kết quả cho một lần chạy: results/<stem> (tạo nếu thiếu)."""
    p = os.path.join(results_dir(), stem)
    assert_write_allowed(p)
    os.makedirs(p, exist_ok=True)
    return p


def is_inside(path: str, parent: str) -> bool:
    """True nếu `path` nằm trong `parent` (an toàn cả khi khác ổ đĩa)."""
    try:
        p = os.path.abspath(path)
        q = os.path.abspath(parent)
        return os.path.commonpath([p, q]) == q
    except ValueError:            # khác ổ đĩa trên Windows → chắc chắn không nằm trong
        return False


def assert_write_allowed(path: str) -> None:
    """Chặn ghi vào thư mục dữ liệu thô (dữ liệu gốc là chỉ đọc)."""
    if is_inside(path, data_dir()):
        raise PermissionError(
            f"từ chối ghi vào {data_dir()} — dữ liệu thô là CHỈ ĐỌC; "
            f"sản phẩm phải nằm trong {results_dir()}")


def describe() -> dict:
    """Mô tả chính sách I/O (đưa vào report/selfcheck)."""
    st = load_settings()
    return dict(app=app_dir(), data=data_dir(), results=results_dir(),
                configs=config_dir(), temp=temp_dir(),
                data_read_only=True,
                data_from=("env" if os.environ.get("PSR_DATA_DIR")
                           else "settings" if st.get("data_dir") else "default"),
                results_from=("env" if os.environ.get("PSR_RESULTS_DIR")
                              else "settings" if st.get("results_dir")
                              else "default"),
                settings_file=settings_path())


def self_check() -> list:
    """Kiểm tra chính sách: đường dẫn tồn tại, data/ bị chặn ghi."""
    bad = []
    ensure_dirs()                      # tạo data/, results/, configs/ nếu thiếu
    d = describe()
    for k in ("app", "data", "results", "configs"):
        if not d[k] or not os.path.isdir(d[k]):
            bad.append(f"{k} không tồn tại: {d[k]}")
    # data/ phải bị chặn
    try:
        assert_write_allowed(os.path.join(d["data"], "x.json"))
        bad.append("không chặn được ghi vào data/")
    except PermissionError:
        pass
    # results/ phải cho phép
    try:
        assert_write_allowed(os.path.join(d["results"], "x", "y.json"))
    except PermissionError as exc:
        bad.append(f"chặn nhầm results/: {exc}")
    # temp không được nằm trong data/
    if is_inside(d["temp"], d["data"]):
        bad.append("thư mục tạm nằm trong data/")
    return bad


if __name__ == "__main__":
    import sys as _s
    try:
        _s.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                            # noqa: BLE001
        pass
    for k, v in describe().items():
        print(f"{k:>8}: {v}")
    print("self_check:", self_check() or "PASS (0 lỗi)")
