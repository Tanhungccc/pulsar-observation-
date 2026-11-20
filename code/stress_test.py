# -*- coding: utf-8 -*-
"""
stress_test.py — CHẠY PIPELINE TRÊN CORPUS DỮ LIỆU "XẤU" (data/stress/).

Mỗi file có một KỲ VỌNG rõ ràng; harness kiểm tra pipeline có hành xử đúng
không (kể cả khi đúng nghĩa là "phải báo lỗi sạch"):
    detect  → phải phát hiện xung / fold ra SNR cao
    nodetect→ chỉ nhiễu: KHÔNG được "phát hiện" (kiểm soát dương tính giả)
    reject  → file hỏng/quá ngắn: phải dừng với chẩn đoán rõ, không crash

    python stress_test.py            # chạy toàn bộ (~2–4 phút)
    python stress_test.py --only B0531

Sản phẩm: results/stress_report.txt, results/stress_matrix.json
"""
from __future__ import annotations

import json
import os
import sys
import time
import traceback

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import psr_detect                                   # noqa: E402
import psr_fil                                      # noqa: E402

STRESS = os.path.join(os.path.dirname(HERE), "data", "stress")
IQ_DIR = os.path.join(os.path.dirname(HERE), "data", "iq")
RESULTS = os.path.join(os.path.dirname(HERE), "results")

# name: (kỳ vọng, p_ref, dm_ref, ghi chú)
CORPUS = {
    "28.fil":            ("any",    None,     None, "6.5 s, 336 kênh, 49 kênh RFI"),
    # LƯU Ý: 2 file dưới lấy từ bộ dữ liệu paper IQRM (về RFI) → chúng là mẫu
    # RFI, KHÔNG chứa tín hiệu pulsar. Đo tại đúng P và DM catalogue chỉ được
    # SNR 3.3 (Crab) / 8.1 (B1828) ⇒ kỳ vọng ĐÚNG là "không được báo phát hiện".
    "B0531+21.fil":      ("nodetect", 0.033392, 56.77,
                          "CRAB cutout của paper IQRM — RFI, không có tín hiệu"),
    "B1828.fil":         ("nodetect", 0.405283, 12.0,
                          "4096 kênh, RFI xung dày — không có tín hiệu"),
    "injected_B0531.fil":("detect", 0.033392, 56.77,
                          "TIÊM pulsar tổng hợp vào NỀN RFI THẬT của Crab"),
    "empty_example.fil": ("nodetect", None,   None, "CHỈ NHIỄU (đối chứng âm)"),
    "small.fil":         ("reject", None,     None, "10 mẫu — file cụt"),
    "tutorial.fil":      ("detect", 0.25,     30.0,
                          "2-BIT đóng gói, sóng 1441–1510 MHz"),
    "crab-giantpulse.sigmf-data": ("detect", None, 56.77,
                          "IQ THÔ (ci16, 20 MS/s) Dwingeloo 25 m — giant pulse Cua"),
    "test_4pol.fits":    ("reject", None,     None, "PSRFITS hỏng: thiếu NPOL, 200 mẫu"),
    "empty.fits":        ("reject", None,     None, "PSRFITS NAXIS2=0 (rỗng)"),
}


def make_injection(src="B0531+21.fil", dst="injected_B0531.fil",
                   period=0.033392, dm=56.77, w50_ms=2.0, snr_target=30.0,
                   seed=7):
    """TIÊM một pulsar tổng hợp vào NỀN RFI THẬT (dữ liệu Crab) rồi ghi .fil.

    Đây là phép kiểm chứng mạnh nhất: không phải dữ liệu sạch tự tạo, mà là
    tín hiệu đã biết nằm trong đúng loại nhiễu/RFI mà kính thật sẽ gặp.
    Nếu pipeline tìm lại được ⇒ chuỗi thuật toán hoạt động trong điều kiện thực.
    """
    from psr_fil import read_fil, write_fil
    from psr_core import dm_delay_s
    srcp = os.path.join(STRESS, src)
    dstp = os.path.join(STRESS, dst)
    if os.path.exists(dstp) and os.path.getsize(dstp) > 0:
        return dstp
    h, dyn = read_fil(srcp)
    d = dyn.astype(np.float64)
    ts, f = h["tsamp_s"], h["freqs_mhz"]
    rng = np.random.default_rng(seed)
    sigma_t = w50_ms * 1e-3 / 2.3548
    duty = max(w50_ms * 1e-3 / period, 1e-4)
    # biên độ tính theo ĐƠN VỊ ADC của dữ liệu thật (sigma từng mẫu)
    sig = 1.4826 * np.median(np.abs(d - np.median(d, axis=1, keepdims=True)),
                             axis=1)
    sigma_adc = float(np.median(sig))
    amp = snr_target * sigma_adc / np.sqrt(len(f) * d.shape[1] * duty)
    delay = dm_delay_s(dm, f, f_ref_mhz=float(f.max()))
    t = np.arange(d.shape[1]) * ts
    npul = int(t[-1] / period)
    for k in range(npul):
        t0 = k * period
        for i in range(len(f)):
            c = t0 + delay[i]
            j0 = int(round((c - 4 * sigma_t) / ts))
            j1 = int(round((c + 4 * sigma_t) / ts)) + 1
            if j1 <= 0 or j0 >= d.shape[1]:
                continue
            j0c, j1c = max(j0, 0), min(j1, d.shape[1])
            z = (t[j0c:j1c] - c) / sigma_t
            d[i, j0c:j1c] += amp * np.exp(-0.5 * z * z)
    # ghi float32: 8-bit sẽ LƯỢNG TỬ HOÁ mất tín hiệu (biên độ ~0.5 count)
    write_fil(dstp, d, dict(source_name=f"INJ: P={period} DM={dm}",
                            nbits=32, nchans=h["nchans"], nifs=1, nbeams=1,
                            telescope_id=6, machine_id=0, data_type=1,
                            tsamp=ts, tstart=h.get("tstart", 60000.0),
                            fch1=float(f[0]), foff=float(f[1] - f[0])))
    return dstp


R: list[dict] = []


def run_one(name: str, expect: str, p_ref, dm_ref, note: str):
    path = os.path.join(STRESS, name)
    if not os.path.exists(path) and os.path.exists(os.path.join(IQ_DIR, name)):
        path = os.path.join(IQ_DIR, name)
    rec = dict(file=name, expect=expect, note=note, size_mb=None,
               dm_ref=dm_ref, p_ref=p_ref, status=None, dm=None, snr=None,
               n_pulses=None, verdict="?", seconds=None, error=None,
               warnings=[])
    if not os.path.exists(path):
        rec["verdict"] = "MISSING"
        R.append(rec)
        return rec
    rec["size_mb"] = round(os.path.getsize(path) / 1e6, 2)
    t0 = time.time()
    try:
        m = psr_detect.detect(path, dm_ref=dm_ref, p_ref=p_ref)
        rec["seconds"] = round(time.time() - t0, 1)
        rec["status"] = m.get("status")
        st = m.get("stage", {})
        rec["dm"] = st.get("dm_scan_best")
        rec["snr"] = st.get("dm_scan_peak_snr")
        rec["n_pulses"] = st.get("n_pulses")
        rec["dm_res"] = st.get("dm_resolution_data")
        rec["train"] = st.get("n_pulses_in_train")
        rec["checks"] = [(c["name"], bool(c["ok"]))
                         for c in m.get("output_checks", [])]
        # ---- phán xử theo kỳ vọng
        if expect == "detect":
            ok = (st.get("dm_scan_peak_snr") or 0) >= 8.0 and                  not st.get("zero_dm_dominated")
            rec["verdict"] = "PASS" if ok else "FAIL(detection yếu)"
        elif expect == "nodetect":
            # Pipeline có thể "thấy" SNR cao do RFI, nhưng phải TỰ KẾT LUẬN
            # đó là RFI (zero_dm_dominated / status=rfi_zero_dm) và không
            # được tạo chuỗi xung cùng pha.
            dominated = bool(st.get("zero_dm_dominated")) or \
                rec["status"] == "rfi_zero_dm"
            ok = dominated or ((st.get("dm_scan_peak_snr") or 0) < 12.0
                               and (st.get("n_pulses_in_train") or 0) == 0)
            rec["verdict"] = "PASS" if ok else "FAIL(dương tính giả)"
        elif expect == "reject":
            ok = rec["status"] in ("too_short", "unreadable", "invalid")
            rec["verdict"] = "PASS" if ok else "FAIL(phải bị từ chối)"
        else:
            rec["verdict"] = "PASS"
    except Exception as e:
        rec["seconds"] = round(time.time() - t0, 1)
        rec["status"] = "CRASH"
        rec["error"] = f"{type(e).__name__}: {e}"
        traceback.print_exc()
        rec["verdict"] = "PASS(chẩn đoán)" if expect == "reject" else "FAIL(crash)"
    R.append(rec)
    return rec


def main(only: str | None = None):
    os.makedirs(RESULTS, exist_ok=True)
    print(f"Corpus: {STRESS}\n")
    try:
        ip = make_injection()
        print(f"→ đã tạo ca TIÊM: {os.path.basename(ip)} "
              f"({os.path.getsize(ip)/1e6:.1f} MB)\n")
    except Exception as e:
        print(f"→ không tạo được ca tiêm: {e!r}\n")
    for name, (expect, p_ref, dm_ref, note) in CORPUS.items():
        if only and only.lower() not in name.lower():
            continue
        print(f"=== {name}  [{expect}]  {note}")
        rec = run_one(name, expect, p_ref, dm_ref, note)
        print(f"    → {rec['verdict']:22} status={rec['status']} "
              f"DM={rec['dm']} SNR={rec['snr']} xung={rec['n_pulses']} "
              f"({rec['seconds']}s)")
        print()

    # ------------------- báo cáo
    lines = ["KIỂM CHỨNG TRÊN CORPUS DỮ LIỆU XẤU", "=" * 78,
             f"{'file':20} {'MB':>6} {'kỳ vọng':>9} {'status':>11} "
             f"{'DM':>7} {'SNR':>7} {'xung':>5}  kết luận"]
    for r in R:
        lines.append(
            f"{r['file']:20} {(r['size_mb'] or 0):6.2f} {r['expect']:>9} "
            f"{str(r['status']):>11} "
            f"{('%.1f' % r['dm']) if r['dm'] is not None else '—':>7} "
            f"{('%.1f' % r['snr']) if r['snr'] is not None else '—':>7} "
            f"{str(r['n_pulses']) if r['n_pulses'] is not None else '—':>5}  "
            f"{r['verdict']}")
    n_ok = sum(1 for r in R if str(r["verdict"]).startswith("PASS"))
    lines += ["=" * 78, f"{n_ok}/{len(R)} file hành xử ĐÚNG kỳ vọng", "",
              "Ghi chú từng file:"]
    for r in R:
        lines.append(f"  • {r['file']}: {r['note']}")
        if r.get("error"):
            lines.append(f"      lỗi/chẩn đoán: {r['error']}")
        if r.get("checks"):
            bad = [c for c, ok in r["checks"] if not ok]
            lines.append(f"      kiểm chứng: {len(r['checks'])} mục"
                         + (f", FAIL: {bad}" if bad else ", tất cả OK"))
    txt = "\n".join(lines)
    print(txt)
    with open(os.path.join(RESULTS, "stress_report.txt"), "w",
              encoding="utf-8") as fh:
        fh.write(txt + "\n")
    with open(os.path.join(RESULTS, "stress_matrix.json"), "w",
              encoding="utf-8") as fh:
        json.dump(R, fh, ensure_ascii=False, indent=2)
    print(f"\n→ results/stress_report.txt, results/stress_matrix.json")
    return 0 if n_ok == len(R) else 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    only = None
    if "--only" in sys.argv:
        only = sys.argv[sys.argv.index("--only") + 1]
    sys.exit(main(only))
