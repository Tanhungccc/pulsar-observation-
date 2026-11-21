# -*- coding: utf-8 -*-
"""make_test_data.py — tạo dữ liệu KIỂM THỬ từ quan sát THẬT.

Mục đích: phủ các đường I/O mà bộ dữ liệu hiện có chưa chạm tới:
    - .fil **4-bit** (đóng gói 2 mẫu/byte)
    - .fil **16-bit** (int16)
    - .fil **32-bit** (float32 — dùng cho phép tiêm tín hiệu)
    - file **dài ~20 phút** có **gap** (kiểm tra xử lý theo đoạn + hiệu năng)

Nguồn: `data/B0329+54.fil` (GREENBURST/GBT, CC-BY-4.0) — **không sửa file gốc**,
chỉ đọc. Mọi file sinh ra ghi kèm `manifest.json` (sha256 nguồn, phép biến đổi).

Chạy:  python make_test_data.py
"""
from __future__ import annotations

import hashlib
import json
import os
import struct
import sys

import numpy as np

import psr_fil
import psr_paths as paths

SRC = os.path.join(paths.data_dir(), "B0329+54.fil")
OUT = os.path.join(paths.data_dir(), "extra")


def _sha256(path: str, head: int = 32 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        left = head
        while left > 0:
            b = fh.read(min(1 << 20, left))
            if not b:
                break
            h.update(b)
            left -= len(b)
    return h.hexdigest()


def _patch_nbits(head: bytes, nbits: int) -> bytes:
    """Sửa trường `nbits` trong header SIGPROC (int32 ngay sau khoá 'nbits')."""
    i = head.find(b"nbits")
    if i < 0:
        raise ValueError("không thấy khoá nbits trong header")
    b = bytearray(head)
    b[i + 5:i + 9] = struct.pack("<i", int(nbits))
    return bytes(b)


def _pack_bits(dyn: np.ndarray, nbits: int) -> bytes:
    """Đóng gói mẫu theo nbits (1/2/4/8 giữ nguyên thứ tự SIGPROC)."""
    # SIGPROC lưu THEO THỜI GIAN: mỗi mốc thời gian là một dãy kênh liên tiếp.
    # (packer cũ ghi theo kênh → đọc lại bị đảo trục, DM rơi về 0 = RFI.)
    d = np.asarray(dyn, dtype=np.float64).T
    # DÙNG PERCENTILE, không dùng min/max: một gai RFI duy nhất làm min/max
    # trải rộng gấp trăm lần → tín hiệu pulsar bị dồn về 0–2 mức (đã gặp: DM
    # đo được 30,5 thay vì 26,5 trên file 4-bit).
    # 4-bit chỉ có 16 mức → clip rất nhẹ (p0,1–99,9); >=16 bit giữ nguyên dải
    pcts = [0.1, 99.9] if nbits <= 4 else [0.0, 100.0]
    lo, hi = (float(v) for v in np.percentile(d, pcts))
    if hi <= lo:
        lo, hi = float(np.min(d)), float(np.max(d))
    span = max(hi - lo, 1e-9)
    if nbits == 4:
        q = np.clip(((d - lo) / span * 15.0).round(), 0, 15).astype(np.uint8).ravel()
        if q.size % 2:
            q = np.append(q, np.uint8(0))
        return ((q[0::2] << 4) | q[1::2]).tobytes()      # 2 mẫu/byte, cao trước
    if nbits == 16:
        q = np.clip((d - lo) / span * 65535.0, 0, 65535).astype("<u2")
        return q.ravel().tobytes()
    if nbits == 8:
        q = np.clip((d - lo) / span * 255.0, 0, 255).astype(np.uint8)
        return q.ravel().tobytes()
    raise ValueError(f"chưa hỗ trợ nbits={nbits}")


def write_custom_fil(dst: str, dyn: np.ndarray, hdr: dict, nbits: int) -> None:
    """Ghi .fil với số bit tuỳ ý: mượn header của write_fil rồi vá nbits."""
    tmp = dst + ".hdr"
    psr_fil.write_fil(tmp, dyn, dict(hdr, nbits=8))
    with open(tmp, "rb") as fh:
        raw = fh.read()
    _, off = psr_fil.read_header(tmp)
    head = _patch_nbits(raw[:off], nbits)
    with open(dst, "wb") as fh:
        fh.write(head)
        fh.write(_pack_bits(dyn, nbits))
    os.remove(tmp)


def main() -> int:
    if not os.path.exists(SRC):
        print(f"THIẾU nguồn: {SRC}")
        return 1
    os.makedirs(OUT, exist_ok=True)
    h, dyn = psr_fil.read_fil(SRC)
    print(f"nguồn: {SRC} → {dyn.shape[0]} kênh × {dyn.shape[1]} mẫu, "
          f"tsamp {h['tsamp_s']*1e6:.0f} µs")
    hdr = dict(source_name="B0329+54 (re-encoded)", nchans=h["nchans"], nifs=1,
               nbeams=1, telescope_id=6, machine_id=0, data_type=1,
               tsamp=h["tsamp_s"], fch1=h["fch1"], foff=h["foff"],
               tstart=h.get("tstart") or 60000.0)
    made = []
    for nbits, name in ((4, "B0329+54_4bit.fil"),
                        (16, "B0329+54_16bit.fil")):
        p = os.path.join(OUT, name)
        write_custom_fil(p, dyn, hdr, nbits)
        made.append(dict(file=name, nbits=nbits, bytes=os.path.getsize(p),
                         transform=f"lượng tử hoá {nbits}-bit"))
        print(f"  ✓ {name}  ({os.path.getsize(p)/1e6:.1f} MB)")

    p32 = os.path.join(OUT, "B0329+54_float32.fil")
    psr_fil.write_fil(p32, dyn.astype(np.float32), dict(hdr, nbits=32))
    made.append(dict(file=os.path.basename(p32), nbits=32,
                     bytes=os.path.getsize(p32), transform="float32 (tiêm được)"))
    print(f"  ✓ {os.path.basename(p32)}  ({os.path.getsize(p32)/1e6:.1f} MB)")

    # file dài ~20 phút: lặp 10 lần, chèn 1 gap để kiểm tra xử lý theo đoạn
    reps, gap_cols = 10, 200
    parts = []
    for k in range(reps):
        parts.append(dyn)
        if k == reps // 2:
            parts.append(np.zeros((dyn.shape[0], gap_cols), dtype=dyn.dtype))
    long_dyn = np.concatenate(parts, axis=1)
    p_long = os.path.join(OUT, "B0329+54_long21s.fil")
    psr_fil.write_fil(p_long, long_dyn, dict(hdr, nbits=8))
    made.append(dict(file=os.path.basename(p_long), nbits=8,
                     bytes=os.path.getsize(p_long),
                     transform=f"lặp {reps}× + gap {gap_cols} mẫu "
                               f"({long_dyn.shape[1]*h['tsamp_s']:.0f} s — kiểm "
                               f"tra đọc nhiều khối + xử lý theo đoạn)"))
    print(f"  ✓ {os.path.basename(p_long)}  ({os.path.getsize(p_long)/1e6:.1f} MB, "
          f"{long_dyn.shape[1]*h['tsamp_s']:.0f} s)")

    man = dict(source=os.path.basename(SRC), source_sha256=_sha256(SRC),
               source_bytes=os.path.getsize(SRC),
               note="Sinh bởi make_test_data.py từ quan sát THẬT (CC-BY-4.0). "
                    "File gốc không bị sửa.",
               files=made)
    with open(os.path.join(OUT, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(man, fh, ensure_ascii=False, indent=2)
    print(f"\nmanifest: {os.path.join(OUT, 'manifest.json')}")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                            # noqa: BLE001
        pass
    sys.exit(main())
