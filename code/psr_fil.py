# -*- coding: utf-8 -*-
"""
psr_fil.py — Đọc/ghi SIGPROC filterbank (.fil) thuần numpy + kiểm chứng.

Đã được GIA CỐ sau khi thử trên dữ liệu thật "xấu" (corpus data/stress/):
    * thêm khoá header gặp thật: `barycentric`, `pulsarcentric`, `auxdims`, …
      (thiếu 2 khoá đầu từng làm 3/6 file mẫu không đọc được)
    * hỗ trợ mẫu ĐÓNG GÓI 1/2/4 bit (tutorial.fil của sigpyproc dùng 2 bit)
    * hỗ trợ nifs > 1 (2 hoặc 4 phân cực) — cộng hoặc chọn 1 phân cực
    * hỗ trợ `signed = 1` (int8) của một số máy
    * file bị CẮT giữa dòng: đọc các dòng đầy đủ + cảnh báo (không crash)
    * dữ liệu PHẲNG (toàn một giá trị) / rỗng: báo lỗi rõ ràng
    * tsamp ≤ 0 hoặc thiếu: cảnh báo (trừ khi strict=True)

Quy ước:
    dyn  -> (nchan, ntime) float32, công suất
    freqs -> MHz, đúng thứ tự trong file (fch1 + foff·i; foff có thể dương)
"""
from __future__ import annotations

import os
import struct

import numpy as np

_STR_KEYS = {"source_name", "rawdatafile"}

# Khoá nguyên 32-bit
_I32_KEYS = {"telescope_id", "machine_id", "data_type", "nbits", "nchans",
             "nifs", "nbeams", "ibeam", "bary", "signed", "sumifs",
             "barycentric", "pulsarcentric", "auxdims", "nbins",
             "bary_corr", "frequency_channel_sequence"}

# Khoá thực 64-bit
_F64_KEYS = {"tsamp", "tstart", "fch1", "foff", "refdm", "period", "fchannel",
             "src_raj", "src_dej", "az_start", "za_start", "ra", "dec",
             "tstart_utc", "epoch"}

_NBITS_DTYPE = {8: np.uint8, 16: np.uint16, 32: np.float32, -32: np.float32}
_PACKED_NBITS = {1, 2, 4}


# ------------------------------------------------------------------ header
def _read_cstr(fh):
    (n,) = struct.unpack("<i", fh.read(4))
    if n < 0 or n > 4096:                     # file hỏng: độ dài vô lý
        raise ValueError(f"độ dài chuỗi header vô lý: {n}")
    return fh.read(n).decode("ascii", "replace")


def read_header(path: str) -> tuple[dict, int]:
    """Đọc header SIGPROC → (dict, offset_byte_của_dữ_liệu)."""
    hdr: dict = {}
    with open(path, "rb") as fh:
        first = _read_cstr(fh)
        if first != "HEADER_START":
            raise ValueError(f"Không phải file SIGPROC (marker đầu là {first[:24]!r})")
        for _ in range(200):                  # chặn header lặp vô hạn
            key = _read_cstr(fh)
            if key == "HEADER_END":
                return hdr, fh.tell()
            if key in _STR_KEYS:
                hdr[key] = _read_cstr(fh)
            elif key in _I32_KEYS:
                (v,) = struct.unpack("<i", fh.read(4))
                hdr[key] = v
            elif key in _F64_KEYS:
                (v,) = struct.unpack("<d", fh.read(8))
                hdr[key] = v
            else:
                raise ValueError(f"Khóa header chưa hỗ trợ: {key!r}")
        raise ValueError("Header không có HEADER_END (file bị cắt?)")


# --------------------------------------------------------- giải mã bit
def _unpack_bits(data: np.ndarray, nbits: int, n_vals: int) -> np.ndarray:
    """Giải mã mẫu đóng gói 1/2/4 bit kiểu SIGPROC (bit cao trước)."""
    per_byte = 8 // nbits
    mask = (1 << nbits) - 1
    shifts = np.arange(8 - nbits, -1, -nbits, dtype=np.uint8)
    out = ((data[:, None] >> shifts[None, :]) & mask).astype(np.uint8)
    return out.ravel()[:n_vals]


# ------------------------------------------------------------------ đọc file
def read_fil(path: str, max_seconds: float | None = None,
             validate: bool = True, pol: int | str = "sum",
             strict: bool = False) -> tuple[dict, np.ndarray]:
    """Đọc .fil → (header chuẩn hoá, dyn (nchan, ntime) float32).

    max_seconds : chỉ đọc N giây đầu.
    pol         : 'sum' (cộng các phân cực) | 'first' | chỉ số phân cực.
    strict      : True → ném lỗi thay vì cảnh báo (dùng cho kiểm thử).
    """
    hdr, off = read_header(path)
    nbits = int(hdr.get("nbits", 8) or 8)
    nifs = max(1, int(hdr.get("nifs", 1) or 1))
    nchans = int(hdr.get("nchans", 0) or 0)
    tsamp = float(hdr.get("tsamp", 0.0) or 0.0)
    warns: list[str] = []

    if nchans < 1:
        raise ValueError(f"nchans = {nchans} không hợp lệ")
    if nchans < 2:
        warns.append(f"nchans = {nchans} < 2 (dữ liệu bất thường)")
    if not (tsamp > 0):
        if strict:
            raise ValueError("tsamp phải > 0")
        warns.append("tsamp ≤ 0 hoặc thiếu → tạm đặt 1.0 s (KHÔNG dùng "
                     "cho khoa học)")
        tsamp = 1.0

    file_size = os.path.getsize(path)
    nbytes = file_size - off
    if nbytes <= 0:
        raise ValueError(f"file không có dữ liệu (header {off} byte, "
                         f"file {file_size} byte)")

    # ---- lấy mẫu thô
    if nbits in _PACKED_NBITS:
        nval_total = (nbytes * 8) // nbits
        rows_file = nval_total // (nchans * nifs)
        if nbytes * 8 - nval_total * nbits:
            warns.append("file CỤT: bit lẻ ở cuối bị bỏ")
        ntime = rows_file if max_seconds is None else min(
            rows_file, int(max_seconds / tsamp))
        if ntime <= 0:
            raise ValueError("không đủ mẫu cho một dòng (file quá nhỏ)")
        raw = np.fromfile(path, dtype=np.uint8, offset=off)
        vals = _unpack_bits(raw, nbits, ntime * nchans * nifs)
        block = vals.astype(np.float32)
        warns.append(f"mẫu {nbits}-bit đóng gói (đã giải mã)")
    else:
        if nbits not in _NBITS_DTYPE:
            raise ValueError(f"nbits = {nbits} không hỗ trợ "
                             f"(hỗ trợ 1/2/4/8/16/32)")
        bytes_per_val = abs(nbits) // 8
        row_bytes = nchans * nifs * bytes_per_val
        rows_file = nbytes // row_bytes
        rem = nbytes - rows_file * row_bytes
        if rem:
            warns.append(f"file CỤT: {rem} byte lẻ ở cuối bị bỏ "
                         f"(không đủ 1 dòng {row_bytes} byte)")
        ntime = rows_file if max_seconds is None else min(
            rows_file, int(max_seconds / tsamp))
        if ntime <= 0:
            have = nbytes
            raise ValueError(f"không đủ dữ liệu cho một dòng: file còn "
                             f"{have} byte, cần {row_bytes} byte/dòng")
        want = ntime * nchans * nifs
        block = np.fromfile(path, dtype=_NBITS_DTYPE[nbits], count=want,
                            offset=off)
        if block.size < want:
            full = block.size // (nchans * nifs)
            warns.append(f"file bị CẮT giữa dòng: chỉ có {full}/{ntime} "
                         f"dòng đầy đủ")
            ntime = full
            block = block[: ntime * nchans * nifs]
        if nbits == 8 and int(hdr.get("signed", 0) or 0) == 1:
            block = block.view(np.int8).astype(np.float32) + 128.0
            warns.append("dữ liệu int8 có dấu (signed=1) → đã dịch +128")
        block = block.astype(np.float32)

    # ---- (ntime, nifs, nchan) → gộp phân cực
    cube = block.reshape(ntime, nifs, nchans)
    if nifs > 1:
        if pol == "sum":
            dyn = cube.sum(axis=1).T
            warns.append(f"nifs = {nifs}: đã CỘNG {nifs} phân cực")
        elif pol == "first":
            dyn = cube[:, 0, :].T
            warns.append(f"nifs = {nifs}: chỉ lấy phân cực 0")
        elif isinstance(pol, int) and 0 <= pol < nifs:
            dyn = cube[:, pol, :].T
            warns.append(f"nifs = {nifs}: lấy phân cực {pol}")
        else:
            raise ValueError(f"pol = {pol!r} không hợp lệ (nifs = {nifs})")
    else:
        dyn = cube[:, 0, :].T
    dyn = np.ascontiguousarray(dyn, dtype=np.float32)

    fch1 = float(hdr.get("fch1", 0.0) or 0.0)
    foff = float(hdr.get("foff", 0.0) or 0.0)
    if foff == 0:
        warns.append("foff = 0 → không xác định được tần số từng kênh")
    if fch1 == 0:
        warns.append("fch1 = 0 → tần số tuyệt đối không xác định")
    freqs = fch1 + foff * np.arange(nchans, dtype=float)

    h = dict(hdr)
    h.update(freqs_mhz=freqs, tsamp_s=tsamp, nchans=nchans, nbits=nbits,
             nifs=nifs, ntime=int(dyn.shape[1]), t_s=float(dyn.shape[1] * tsamp),
             data_offset=off, data_file_bytes=file_size,
             source=hdr.get("source_name", "?"))
    if validate:
        h["validation"] = validate_dyn(dyn, h)
        h["read_warnings"] = warns + h["validation"]["warnings"]
        if strict and not h["validation"]["ok"]:
            raise ValueError("Dữ liệu không đạt kiểm chứng: "
                             + "; ".join(h["validation"]["problems"]))
    else:
        h["read_warnings"] = warns
    return h, dyn


# --------------------------------------------------------------- kiểm chứng
def validate_dyn(dyn: np.ndarray, h: dict) -> dict:
    """Kiểm chứng dữ liệu ĐẦU VÀO → {ok, problems, warnings, stats}."""
    problems: list[str] = []
    warnings: list[str] = []
    if dyn.ndim != 2:
        problems.append(f"dyn.ndim = {dyn.ndim} (cần 2)")
    fs = np.asarray(dyn, dtype=np.float64)
    if fs.size == 0:
        problems.append("mảng rỗng (không có mẫu)")
        return {"ok": False, "problems": problems, "warnings": warnings,
                "stats": {}}
    if not np.isfinite(fs).all():
        problems.append("có NaN/Inf trong dữ liệu")
    if float(fs.std()) == 0.0:
        problems.append("dữ liệu PHẲNG hoàn toàn (một giá trị) — không phải "
                        "quan sát hợp lệ")

    cmean = fs.mean(axis=1)
    med_c = np.median(cmean)
    rms_c = 1.4826 * np.median(np.abs(cmean - med_c)) + 1e-12
    hot = np.where(np.abs(cmean - med_c) > 5 * rms_c)[0]
    if len(hot) > 0:
        warnings.append(f"{len(hot)}/{len(cmean)} kênh lệch > 5σ "
                        f"(RFI băng hẹp hoặc kênh chết)")
    if len(hot) > 0.4 * len(cmean):
        warnings.append("hơn 40% kênh bất thường — bandpass/RFI rất xấu")

    tmean = fs.mean(axis=0)
    med_t = np.median(tmean)
    rms_t = 1.4826 * np.median(np.abs(tmean - med_t)) + 1e-12
    z = (tmean - med_t) / rms_t
    rfi_frac = float(np.mean(np.abs(z) > 5))
    if rfi_frac > 0.01:
        warnings.append(f"{100*rfi_frac:.1f}% mẫu vượt 5σ (RFI xung)")

    if h.get("nbits") == 8 and float(fs.max()) >= 254:
        warnings.append("giá trị chạm 254/255 — ADC có thể đã bão hoà")
    if h.get("ntime", 0) and h.get("ntime") < 100:
        warnings.append(f"chỉ có {h['ntime']} mẫu — quá ngắn để fold")

    stats = dict(mean=float(fs.mean()), std=float(fs.std()),
                 tmin=float(fs.min()), tmax=float(fs.max()),
                 n_chan_odd=int(len(hot)), rfi_frac=rfi_frac,
                 nchan=int(fs.shape[0]), ntime=int(fs.shape[1]))
    return {"ok": not problems, "problems": problems, "warnings": warnings,
            "stats": stats}


# ------------------------------------------------------------------ ghi
def write_fil(path: str, dyn: np.ndarray, hdr: dict):
    """Ghi .fil từ dyn (nchan, ntime).

    nbits = 8  → uint8  (như đa số file thật)
    nbits = 32 → float32 (dùng cho phép TIÊM tín hiệu: không bị lượng tử hoá
                 nuốt mất tín hiệu yếu — đã gặp với dữ liệu 8-bit)
    """
    dyn = np.asarray(dyn)
    nchans, ntime = dyn.shape
    nbits = int(hdr.get("nbits", 8))
    with open(path, "wb") as fh:
        def s(text):
            b = text.encode("ascii")
            fh.write(struct.pack("<i", len(b)) + b)

        s("HEADER_START")
        s("source_name"); s(hdr.get("source_name", "TEST"))
        for key in ("nbits", "nchans", "nifs", "nbeams", "machine_id",
                    "telescope_id", "data_type", "barycentric", "signed"):
            val = nbits if key == "nbits" else int(hdr.get(key, 0))
            s(key); fh.write(struct.pack("<i", int(val)))
        for key in ("tsamp", "tstart", "fch1", "foff", "refdm"):
            s(key); fh.write(struct.pack("<d", float(hdr.get(key, 0.0))))
        s("HEADER_END")
        if nbits == 32:
            fh.write(dyn.T.astype(np.float32).tobytes())
        else:
            fh.write(np.clip(dyn.T, 0, 255).astype(np.uint8).tobytes())
    return path
