# -*- coding: utf-8 -*-
"""psr_housekeeping.py — QUẢN LÝ DỮ LIỆU & CHỐNG TRÀN Ổ ĐĨA.

Vì sao cần: mỗi lần chạy pipeline sinh **một thư mục** `results/<YYYYMMDD_HHMMSS>/`
(3–4 hình + JSON + TXT), mỗi lần `gui_verify`/`acceptance_test` sinh thêm vài
thư mục nữa. Không dọn định kỳ thì `results/` phình dần và có ngày đầy ổ.

Nguyên tắc an toàn (được kiểm bằng --selftest):
  1. **Chỉ** đụng vào thư mục con của `results/` có tên đúng dạng `YYYYMMDD_HHMMSS`.
     Mọi mục khác (tệp rời, thư mục có tên khác) **không bao giờ** bị xoá.
  2. **Không bao giờ** xoá `data/` (dữ liệu thô) — công cụ chỉ đọc để báo dung lượng.
  3. Mặc định **chạy thử (dry-run)**: phải thêm `--apply` mới xoá thật.
  4. Luôn giữ `--keep N` lần chạy MỚI NHẤT (mặc định 15) + danh sách `--protect`.
  5. Từ chối chạy nếu `results/` không nằm trong thư mục ứng dụng (trừ `--force`).

Dùng:
    python psr_housekeeping.py --check              # xem dung lượng, không xoá
    python psr_housekeeping.py --clean              # chạy thử, in việc sẽ xoá
    python psr_housekeeping.py --clean --apply      # xoá thật
    python psr_housekeeping.py --clean --apply --keep 8 --max-mb 200
    python psr_housekeeping.py --selftest
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
import time

RUN_RE = re.compile(r"^\d{8}_\d{6}")
DEFAULT_KEEP = 15


# ------------------------------------------------------------------ tiện ích
def dir_size(path: str) -> int:
    t = 0
    for r, _d, fs in os.walk(path):
        for f in fs:
            try:
                t += os.path.getsize(os.path.join(r, f))
            except OSError:
                pass
    return t


def human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024 or unit == "TB":
            return f"{n:.1f} {unit}"
        n /= 1024.0
    return f"{n:.1f} TB"


def list_runs(results_dir: str) -> list[dict]:
    """Chỉ các thư mục có tên dạng YYYYMMDD_HHMMSS (bỏ qua mọi thứ khác)."""
    out = []
    if not os.path.isdir(results_dir):
        return out
    for name in os.listdir(results_dir):
        p = os.path.join(results_dir, name)
        if not os.path.isdir(p) or not RUN_RE.match(name):
            continue
        try:
            st = os.stat(p)
        except OSError:
            continue
        out.append(dict(name=name, path=p, size=dir_size(p),
                        mtime=st.st_mtime, t=time.strftime(
                            "%Y-%m-%d %H:%M", time.localtime(st.st_mtime))))
    out.sort(key=lambda d: d["name"], reverse=True)      # mới nhất trước
    return out


# ------------------------------------------------------------------ kế hoạch
def plan_cleanup(results_dir: str, keep: int = DEFAULT_KEEP,
                 max_mb: float | None = None,
                 protect: tuple[str, ...] = ()) -> dict:
    """Tính danh sách cần xoá: giữ `keep` lần mới nhất + `protect`.

    Nếu `max_mb` được đặt: xoá thêm (vẫn theo thứ tự cũ→mới) cho tới khi
    tổng dung lượng ≤ max_mb, nhưng **luôn giữ ít nhất 1** lần chạy.
    """
    runs = list_runs(results_dir)
    keep = max(0, int(keep))
    protected = {n for n in protect}
    keep_names = {d["name"] for d in runs[:keep]} | protected
    victims = [d for d in runs if d["name"] not in keep_names]
    total = sum(d["size"] for d in runs)
    if max_mb is not None:
        # ngân sách dung lượng: xoá dần từ CŨ nhất, nhưng TUYỆT ĐỐI giữ
        # lần chạy mới nhất (runs[0]) và các mục --protect
        budget = float(max_mb) * 1e6
        newest = runs[0]["name"] if runs else None
        remaining = total
        extra: list[dict] = []
        for d in sorted(victims + [x for x in runs if x["name"] in keep_names],
                        key=lambda x: x["name"]):
            if remaining <= budget:
                break
            if d["name"] == newest or d["name"] in protected:
                continue
            extra.append(d)
            remaining -= d["size"]
        victims = extra
    seen, uniq = set(), []
    for d in victims:
        if d["name"] not in seen:
            seen.add(d["name"])
            uniq.append(d)
    return dict(n_runs=len(runs), total=total, keep=keep,
                keep_names=sorted(keep_names), victims=uniq,
                freed=sum(d["size"] for d in uniq),
                remain=total - sum(d["size"] for d in uniq))


def apply_cleanup(plan: dict, verbose: bool = True) -> int:
    """Xoá thật các thư mục trong kế hoạch. Trả về số byte đã giải phóng."""
    freed = 0
    for d in plan["victims"]:
        try:
            shutil.rmtree(d["path"])
            freed += d["size"]
            if verbose:
                print(f"  − {d['name']}  ({human(d['size'])})")
        except OSError as exc:
            print(f"  ! không xoá được {d['name']}: {exc}")
    return freed


# ------------------------------------------------------------------- báo cáo
def audit(results_dir: str, data_dir: str | None = None) -> dict:
    runs = list_runs(results_dir)
    others = []
    if os.path.isdir(results_dir):
        for name in os.listdir(results_dir):
            p = os.path.join(results_dir, name)
            if os.path.isdir(p) and not RUN_RE.match(name):
                others.append((name, dir_size(p)))
            elif os.path.isfile(p):
                others.append((name, os.path.getsize(p)))
    info = dict(results_dir=results_dir, n_runs=len(runs),
                runs_bytes=sum(d["size"] for d in runs),
                other_bytes=sum(s for _n, s in others),
                oldest=runs[-1]["name"] if runs else None,
                newest=runs[0]["name"] if runs else None,
                biggest=sorted(runs, key=lambda d: -d["size"])[:5])
    if data_dir and os.path.isdir(data_dir):
        info["data_bytes"] = dir_size(data_dir)
        files = []
        for r, _d, fs in os.walk(data_dir):
            for f in fs:
                p = os.path.join(r, f)
                try:
                    files.append((os.path.getsize(p), p))
                except OSError:
                    pass
        files.sort(reverse=True)
        info["data_biggest"] = [(human(s), os.path.relpath(p, data_dir))
                                for s, p in files[:5]]
    try:
        du = shutil.disk_usage(results_dir if os.path.isdir(results_dir) else ".")
        info["disk_free"] = du.free
        info["disk_total"] = du.total
    except OSError:
        pass
    return info


def report(info: dict) -> str:
    L = ["=== QUẢN LÝ DỮ LIỆU PULSAR OBSERVATION ==="]
    L.append(f"results: {info['results_dir']}")
    L.append(f"  {info['n_runs']} lần chạy · {human(info['runs_bytes'])}"
             + (f" · mục khác {human(info['other_bytes'])}" if info['other_bytes'] else ""))
    if info["oldest"]:
        L.append(f"  cũ nhất {info['oldest']} → mới nhất {info['newest']}")
    for d in info["biggest"]:
        L.append(f"    {d['name']}  {human(d['size'])}  ({d['t']})")
    if info.get("data_bytes"):
        L.append(f"data (CHỈ ĐỌC, không bao giờ bị xoá): {human(info['data_bytes'])}")
        for s, p in info.get("data_biggest", []):
            L.append(f"    {s:>9}  {p}")
    if info.get("disk_free"):
        L.append(f"ổ đĩa: còn trống {human(info['disk_free'])} / "
                 f"{human(info['disk_total'])} "
                 f"({100*info['disk_free']/info['disk_total']:.1f} %)")
    return "\n".join(L)


# ------------------------------------------------------------------ selftest
def selftest() -> int:
    import tempfile
    ok = n = 0

    def chk(name, cond, detail=""):
        nonlocal ok, n
        n += 1
        ok += bool(cond)
        print(f"  [{'PASS' if cond else 'FAIL'}] {name}"
              + (f" — {detail}" if detail else ""))

    with tempfile.TemporaryDirectory() as td:
        res = os.path.join(td, "results")
        os.makedirs(res)
        # 20 lần chạy giả, mỗi lần 1 MB; + 2 mục KHÔNG được xoá
        for i in range(1, 21):
            d = os.path.join(res, f"20260101_0000{i:02d}")
            os.makedirs(d)
            with open(os.path.join(d, "detect_report.txt"), "w") as fh:
                fh.write("x" * (1 << 20))
        os.makedirs(os.path.join(res, "_gio_test_res"))
        with open(os.path.join(res, "stress_report.txt"), "w") as fh:
            fh.write("keep me")
        data = os.path.join(td, "data")
        os.makedirs(data)
        with open(os.path.join(data, "raw.fil"), "wb") as fh:
            fh.write(b"0" * 4096)

        chk("đếm đúng 20 lần chạy (bỏ qua mục khác)", len(list_runs(res)) == 20,
            f"{len(list_runs(res))}")
        plan = plan_cleanup(res, keep=5)
        chk("keep=5 → xoá đúng 15 thư mục", len(plan["victims"]) == 15,
            f"{len(plan['victims'])}")
        chk("giữ 5 thư mục MỚI NHẤT",
            plan["keep_names"] == sorted(d["name"] for d in list_runs(res)[:5]),
            str(plan["keep_names"][:2]) + "…")
        chk("KHÔNG bao giờ đưa '_gio_test_res' hay tệp rời vào danh sách xoá",
            all(not v["name"].startswith("_") for v in plan["victims"]))
        plan_p = plan_cleanup(res, keep=5, protect=("20260101_000002",))
        chk("--protect giữ đúng thư mục được chỉ định",
            "20260101_000002" in plan_p["keep_names"]
            and all(v["name"] != "20260101_000002" for v in plan_p["victims"]))
        n_before = len(list_runs(res))
        freed = apply_cleanup(plan, verbose=False)
        chk("xoá thật đúng số thư mục còn lại = keep",
            len(list_runs(res)) == 5 and freed > 0,
            f"còn {len(list_runs(res))} · giải phóng {human(freed)}")
        chk("data/ KHÔNG bị đụng", os.path.exists(os.path.join(data, "raw.fil")))
        chk("tệp rời trong results/ KHÔNG bị đụng",
            os.path.exists(os.path.join(res, "stress_report.txt")))
        chk("thư mục tên khác dạng ngày KHÔNG bị đụng",
            os.path.isdir(os.path.join(res, "_gio_test_res")))
        runs_now = list_runs(res)
        plan2 = plan_cleanup(res, keep=0, max_mb=0.5)
        newest = runs_now[0]["name"]
        chk("--max-mb KHÔNG BAO GIỜ xoá lần chạy mới nhất",
            all(v["name"] != newest for v in plan2["victims"]),
            f"mới nhất {newest} · xoá {len(plan2['victims'])}/{len(runs_now)}")
        chk("--max-mb chỉ xoá tới khi vừa ngân sách (không xoá sạch)",
            len(plan2["victims"]) < len(runs_now), f"{len(plan2['victims'])} mục")

    print(f"\n{ok}/{n} kiểm tra PASS")
    return 0 if ok == n else 1


# ---------------------------------------------------------------------- CLI
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Dọn results/ an toàn, chống tràn ổ")
    ap.add_argument("--results", default=None, help="thư mục results (mặc định của app)")
    ap.add_argument("--data", default=None, help="thư mục data (chỉ để báo dung lượng)")
    ap.add_argument("--check", action="store_true", help="chỉ báo cáo, không xoá")
    ap.add_argument("--clean", action="store_true", help="lập kế hoạch dọn")
    ap.add_argument("--apply", action="store_true", help="XOÁ THẬT (mặc định chỉ chạy thử)")
    ap.add_argument("--keep", type=int, default=DEFAULT_KEEP,
                    help=f"số lần chạy mới nhất giữ lại (mặc định {DEFAULT_KEEP})")
    ap.add_argument("--max-mb", type=float, default=None,
                    help="ngân sách dung lượng results/ (MB)")
    ap.add_argument("--protect", nargs="*", default=[], help="tên thư mục phải giữ")
    ap.add_argument("--force", action="store_true",
                    help="cho phép chạy ngoài thư mục ứng dụng")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()

    if a.results:
        res = a.results
    else:
        try:
            import psr_paths
            res = psr_paths.results_dir()
            a.data = a.data or psr_paths.data_dir()
        except Exception:                    # noqa: BLE001
            res = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "results")
    res = os.path.abspath(res)
    if not a.force:
        app_dir = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
        if not os.path.abspath(res).startswith(app_dir):
            print(f"TỪ CHỐI: {res} không nằm trong {app_dir} (dùng --force nếu chắc chắn)")
            return 3

    info = audit(res, a.data)
    print(report(info))
    if a.check or not a.clean:
        if not a.clean:
            print("\n(chỉ báo cáo — thêm --clean để xem kế hoạch dọn, "
                  "--clean --apply để xoá thật)")
        return 0

    plan = plan_cleanup(res, keep=a.keep, max_mb=a.max_mb, protect=tuple(a.protect))
    print(f"\nKẾ HOẠCH: giữ {a.keep} lần mới nhất"
          + (f" + {len(a.protect)} mục được bảo vệ" if a.protect else "")
          + (f" · ngân sách {a.max_mb:g} MB" if a.max_mb else ""))
    if not plan["victims"]:
        print("  không có gì cần xoá.")
        return 0
    print(f"  sẽ xoá {len(plan['victims'])} thư mục · {human(plan['freed'])} "
          f"→ còn {human(plan['remain'])}")
    if not a.apply:
        for d in plan["victims"][:10]:
            print(f"    · {d['name']}  {human(d['size'])}")
        if len(plan["victims"]) > 10:
            print(f"    … và {len(plan['victims'])-10} mục nữa")
        print("\nCHẠY THỬ — thêm --apply để xoá thật.")
        return 0
    print("  đang xoá:")
    freed = apply_cleanup(plan)
    print(f"\nĐÃ XOÁ {human(freed)} · results/ còn {human(plan['remain'])}")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                        # noqa: BLE001
        pass
    sys.exit(main())
