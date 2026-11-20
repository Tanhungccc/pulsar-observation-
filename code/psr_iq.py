# -*- coding: utf-8 -*-
"""
psr_iq.py — Đọc IQ THÔ (chưa channelize) → phổ động. Đây là đường đi thật của
tín hiệu: [dây/feeds] → SDR/backend → **cặp I/Q** → FFT → kênh tần số.

Vì sao cần module riêng: filterbank/.fil đã được channelize sẵn; còn dữ liệu
"từ dây signal vào máy" là **mẫu phức liên tiếp**. Muốn kiểm chứng toàn chuỗi
ta phải tự làm bước A1 (channelize) từ đúng dữ liệu thô đó.

Định dạng hỗ trợ (tự nhận):
    SigMF   : <tên>.sigmf-data + <.sigmf-meta>   (ci8 / ci16_le / cf32_le)
    SDR     : rtl_sdr .cu8/.bin, GQRX .raw, .cs8, .cs16, .cf32
    WAV I/Q : 2 kênh (I,Q) 8 hoặc 16 bit
    .npy    : mảng phức (dùng cho test)

Bước xử lý (đều là thứ phải làm với dữ liệu thật):
    1. Đọc mẫu phức (giữ nguyên giá trị thô)
    2. Bỏ DC spike: trừ trung bình phức
    3. Cân bằng I/Q (biên độ + pha) — SDR thật luôn lệch vài %
    4. Channelize: FFT N điểm có cửa sổ Hann → công suất từng kênh
    5. Gộp navg khung → tsamp; hoán vị Nyquist về thứ tự tần số tăng
"""
from __future__ import annotations

import json
import os

import numpy as np

_DTYPES = {
    "cu8": np.uint8, "ci8": np.int8, "ci16_le": np.dtype("<i2"),
    "ci16_be": np.dtype(">i2"), "cf32_le": np.dtype("<f4"),
    "cf32_be": np.dtype(">f4"),
}
_ALIAS = {  # đuôi file → datatype (khi không có SigMF meta)
    ".cu8": "cu8", ".cs8": "ci8", ".ci8": "ci8", ".cu16": "ci16_le",
    ".cs16": "ci16_le", ".ci16": "ci16_le", ".cf32": "cf32_le",
    ".fc32": "cf32_le", ".raw": "ci16_le", ".bin": "cu8",
}


def read_sigmf_meta(path: str) -> dict:
    """Đọc .sigmf-meta (JSON) → dict gọn: datatype, fs, fc, mô tả, thời điểm."""
    if path.endswith(".sigmf-data"):
        meta_path = path[: -len(".sigmf-data")] + ".sigmf-meta"
    elif os.path.exists(path + ".sigmf-meta"):
        meta_path = path + ".sigmf-meta"
    else:
        return {}          # KHÔNG thử mở .wav/.npy như JSON (đã gây lỗi)
    if not os.path.exists(meta_path):
        return {}
    try:
        with open(meta_path, encoding="utf-8") as fh:
            m = json.load(fh)
    except Exception:
        return {}
    g = m.get("global", {})
    caps = m.get("captures") or [{}]
    cap0 = caps[0] if caps else {}
    out = {
        "datatype": g.get("core:datatype", ""),
        "fs_hz": float(g.get("core:sample_rate", 0) or 0),
        "fc_hz": float(cap0.get("core:frequency", 0) or 0),
        "description": g.get("core:description", ""),
        "author": g.get("core:author", ""),
        "license": g.get("core:license", ""),
        "datetime": cap0.get("core:datetime") or g.get("dt:datetime"),
        "raw": g,
    }
    return out


def _load_iq_raw(path: str, datatype: str, max_samples: int | None):
    """Đọc mảng phức từ file thô theo datatype SigMF."""
    n_bytes = os.path.getsize(path)
    if datatype in ("ci8", "cu8"):
        if datatype == "cu8":
            raw = np.fromfile(path, dtype=np.uint8)
            raw = raw.astype(np.int16) - 127
        else:
            raw = np.fromfile(path, dtype=np.int8).astype(np.int16)
        n = raw.size // 2
        if max_samples:
            n = min(n, max_samples)
        iq = raw[: 2 * n].reshape(n, 2).astype(np.float32)
        iq = iq[:, 0] + 1j * iq[:, 1]
        return iq, 8
    if datatype in ("ci16_le", "ci16_be"):
        raw = np.fromfile(path, dtype=_DTYPES[datatype])
        n = raw.size // 2
        if max_samples:
            n = min(n, max_samples)
        iq = raw[: 2 * n].reshape(n, 2).astype(np.float32)
        return (iq[:, 0] + 1j * iq[:, 1]), 16
    if datatype in ("cf32_le", "cf32_be"):
        raw = np.fromfile(path, dtype=_DTYPES[datatype])
        n = raw.size // 2
        if max_samples:
            n = min(n, max_samples)
        iq = raw[: 2 * n].reshape(n, 2).astype(np.float32)
        return (iq[:, 0] + 1j * iq[:, 1]), 32
    raise ValueError(f"datatype SigMF chưa hỗ trợ: {datatype!r}")


def _load_wav(path: str, max_samples: int | None):
    import wave
    with wave.open(path, "rb") as w:
        nch, sw, fs = w.getnchannels(), w.getsampwidth(), w.getframerate()
        if nch != 2:
            raise ValueError(f"WAV IQ cần 2 kênh (I,Q), file có {nch}")
        n = w.getnframes()
        if max_samples:
            n = min(n, max_samples)
        buf = w.readframes(n)
    if sw == 1:
        a = (np.frombuffer(buf, dtype=np.uint8).astype(np.int16) - 127).astype(np.float32)
    elif sw == 2:
        a = np.frombuffer(buf, dtype="<i2").astype(np.float32)
    else:
        raise ValueError(f"WAV {sw*8}-bit chưa hỗ trợ")
    a = a.reshape(-1, 2)
    return (a[:, 0] + 1j * a[:, 1]), fs, sw * 8


def fix_iq(iq: np.ndarray) -> tuple[np.ndarray, dict]:
    """Sửa lỗi IQ thật: DC offset + mất cân bằng biên độ/pha giữa I và Q.

    Mất cân bằng tạo ảnh gương (mirror) tại -f, làm bẩn phổ nửa dưới.
    Cách sửa: ước lượng hệ số Gram-Schmidt (thuần numpy).
        I' = I − mean(I);  Q' = Q − mean(Q)
        a = <I'Q'>/<I'I'>  ; Q'' = Q' − a·I'  ; tỉ lệ chuẩn hoá lại
    """
    info = {}
    dc = complex(iq.mean())
    x = iq - dc
    i = x.real.copy(); q = x.imag.copy()
    si = i.std() + 1e-20
    sq = q.std() + 1e-20
    info["dc_magnitude"] = float(abs(dc))
    info["iq_amplitude_ratio"] = float(si / sq)
    a = float((i * q).mean() / (i * i).mean()) if i.any() else 0.0
    q2 = q - a * i
    info["iq_phase_sin"] = a
    # chuẩn hoá về cùng công suất
    q2 *= si / (q2.std() + 1e-20)
    out = i + 1j * q2
    return out.astype(np.complex64), info


def channelize_iq(iq: np.ndarray, fs_hz: float, fc_hz: float,
                  nchan: int = 256, navg: int = 1, window: str = "hann",
                  apply_iq_fix: bool = True):
    """IQ → (dyn (nchan, ntime) float32, freqs_mhz, tsamp_s, meta).

    navg: gộp bao nhiêu khung FFT thành 1 mẫu thời gian.
    Thời gian mỗi mẫu = nchan·navg/fs.
    """
    info = {}
    x = iq
    if apply_iq_fix:
        x, info = fix_iq(iq)
    nblk = len(x) // nchan
    if nblk < 1:
        raise ValueError(f"quá ít mẫu ({len(x)}) cho {nchan} kênh")
    x = x[: nblk * nchan].reshape(nblk, nchan)
    win = np.ones(nchan, dtype=np.float32)
    if window == "hann":
        win = np.hanning(nchan).astype(np.float32)
    spec = np.fft.fftshift(np.fft.fft(x * win[None, :], axis=1), axes=1)
    p = (np.abs(spec) ** 2).astype(np.float32)
    # chuẩn hoá để "nhiễu trắng" có trung bình 1 (tiện so sánh)
    p /= max(float(np.median(p)), 1e-20)
    if navg > 1:
        m = (p.shape[0] // navg) * navg
        p = p[:m].reshape(-1, navg, nchan).mean(axis=1)
    dyn = np.ascontiguousarray(p.T)                  # (nchan, ntime)
    df = fs_hz / nchan
    freqs = (fc_hz + (np.arange(nchan) - (nchan - 1) / 2.0) * df) / 1e6
    tsamp = nchan * navg / fs_hz
    meta = dict(nchan=nchan, navg=navg, fs_hz=fs_hz, fc_hz=fc_hz,
                df_hz=df, tsamp_s=tsamp, ntime=dyn.shape[1],
                t_s=dyn.shape[1] * tsamp, window=window,
                iq_fix=info, iq_dtype_bits=getattr(iq, "dtype", None))
    return dyn, freqs, tsamp, meta


def read_iq(path: str, max_seconds: float | None = None,
            datatype: str | None = None, fs_hz: float | None = None,
            fc_hz: float | None = None):
    """Đọc IQ thô → (iq complex64, header). Tự nhận định dạng từ SigMF/đuôi file."""
    hdr = dict(path=path, datatype=None, fs_hz=fs_hz, fc_hz=fc_hz,
               source="?", warnings=[])
    # 0) WAV / NPY: tự mô tả, KHÔNG cần datatype SigMF
    if path.lower().endswith(".wav"):
        maxs = int(max_seconds * fs_hz) if (max_seconds and fs_hz) else None
        iq, fs, bits = _load_wav(path, maxs)
        hdr.update(fs_hz=fs, datatype=f"wav{bits}", n_samples=len(iq),
                   source="WAV I/Q")
        if not hdr["fc_hz"]:
            hdr["fc_hz"] = 0.0
            hdr["warnings"].append("WAV không có tần số tâm — phải khai báo "
                                   "(fc_hz=...)")
        return iq, hdr
    if path.lower().endswith(".npy"):
        iq = np.load(path)
        hdr.update(datatype=str(iq.dtype), n_samples=len(iq),
                   fs_hz=fs_hz or 0.0, fc_hz=fc_hz or 0.0, source="NPY")
        if max_seconds and hdr["fs_hz"]:
            iq = iq[: int(max_seconds * hdr["fs_hz"])]
        return iq.astype(np.complex64), hdr

    # 1) SigMF
    sm = read_sigmf_meta(path)
    if sm:
        hdr.update(datatype=sm.get("datatype") or datatype,
                   fs_hz=sm.get("fs_hz") or fs_hz,
                   fc_hz=sm.get("fc_hz") or fc_hz,
                   source=sm.get("description") or "SigMF",
                   sigmf=sm)
    else:
        ext = os.path.splitext(path)[1].lower()
        hdr["datatype"] = datatype or _ALIAS.get(ext)
        if not hdr["datatype"]:
            hdr["warnings"].append(f"không đoán được datatype từ đuôi {ext!r}")
            raise ValueError(f"cần biết datatype cho {os.path.basename(path)} "
                             f"(SigMF meta hoặc tham số datatype)")
    dt = hdr["datatype"]

    # 2) WAV
    if path.lower().endswith(".wav"):
        maxs = int(max_seconds * fs_hz) if (max_seconds and fs_hz) else None
        iq, fs, bits = _load_wav(path, maxs)
        hdr.update(fs_hz=fs, datatype=f"wav{bits}")
        if not hdr["fc_hz"]:
            hdr["fc_hz"] = 0.0
            hdr["warnings"].append("WAV không có tần số tâm — phải tự khai báo")
        hdr["n_samples"] = len(iq)
        return iq, hdr

    # 3) .npy (mảng phức)
    if path.lower().endswith(".npy"):
        iq = np.load(path)
        hdr.update(datatype=str(iq.dtype), n_samples=len(iq))
        hdr["fs_hz"] = fs_hz or 0.0
        hdr["fc_hz"] = fc_hz or 0.0
        return iq.astype(np.complex64), hdr

    maxs = int(max_seconds * hdr["fs_hz"]) if (max_seconds and hdr["fs_hz"]) else None
    iq, bits = _load_iq_raw(path, dt, maxs)
    hdr.update(n_samples=len(iq), bits=bits)
    if not hdr["fs_hz"]:
        hdr["warnings"].append("không có sample_rate (SigMF/khai báo)")
    if not hdr["fc_hz"]:
        hdr["warnings"].append("không có tần số tâm (SigMF/khai báo)")
    return iq, hdr


def read_iq_as_dyn(path: str, nchan: int = 256, navg: int = 1,
                   max_seconds: float | None = None, **kw):
    """Đường tắt: IQ thô → (header, dyn) đúng định dạng pipeline cần."""
    iq, h = read_iq(path, max_seconds=max_seconds, **kw)
    dyn, freqs, tsamp, meta = channelize_iq(iq, h["fs_hz"], h["fc_hz"],
                                            nchan=nchan, navg=navg,
                                            apply_iq_fix=True)
    out = dict(source=h.get("source", "?"), freqs_mhz=freqs, tsamp_s=tsamp,
               nchans=nchan, nifs=1, nbits=h.get("bits", 0),
               ntime=dyn.shape[1], t_s=meta["t_s"], data_offset=0,
               data_file_bytes=os.path.getsize(path),
               read_warnings=h["warnings"] + [
                   f"IQ {h['datatype']} @ {h['fs_hz']/1e6:.1f} MS/s, "
                   f"tâm {h['fc_hz']/1e6:.1f} MHz",
                   f"channelize: {nchan} kênh, navg={navg}, "
                   f"tsamp={tsamp*1e6:.1f} µs",
               ],
               iq_meta=h, iq_fix=meta["iq_fix"])
    from psr_fil import validate_dyn
    out["validation"] = validate_dyn(dyn, out)
    return out, dyn


# ---------------------------------------------------------------- ghi (test)
def write_sigmf(path_stem: str, iq: np.ndarray, fs_hz: float, fc_hz: float,
                datatype: str = "ci16_le", description: str = "synthetic IQ"):
    """Ghi cặp .sigmf-data/.sigmf-meta — để tự kiểm thử đường đọc IQ."""
    iq = np.asarray(iq)
    data_path = path_stem + ".sigmf-data"
    if datatype == "ci16_le":
        a = np.empty(2 * len(iq), dtype="<i2")
        a[0::2] = np.clip(np.rint(iq.real), -32768, 32767).astype("<i2")
        a[1::2] = np.clip(np.rint(iq.imag), -32768, 32767).astype("<i2")
    elif datatype == "cf32_le":
        a = np.empty(2 * len(iq), dtype="<f4")
        a[0::2] = iq.real; a[1::2] = iq.imag
    elif datatype == "cu8":
        a = np.empty(2 * len(iq), dtype=np.uint8)
        a[0::2] = np.clip(np.rint(iq.real + 127), 0, 255).astype(np.uint8)
        a[1::2] = np.clip(np.rint(iq.imag + 127), 0, 255).astype(np.uint8)
    else:
        raise ValueError(datatype)
    a.tofile(data_path)
    meta = {"global": {"core:datatype": datatype, "core:sample_rate": fs_hz,
                       "core:version": "1.0.0",
                       "core:description": description},
            "captures": [{"core:sample_offset": 0,
                          "core:frequency": fc_hz,
                          "core:datetime": "2026-01-01T00:00:00Z"}],
            "annotations": []}
    with open(path_stem + ".sigmf-meta", "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=2)
    return data_path


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    # tự kiểm thử: sinh IQ có tín hiệu đã tán sắc + méo IQ, rồi đọc lại
    fs, fc, n = 2.4e6, 1420e6, 400_000
    rng = np.random.default_rng(0)
    t = np.arange(n) / fs
    iq = (rng.normal(0, 1, n) + 1j * rng.normal(0, 1, n)) * 0.5
    tone = np.exp(2j * np.pi * 12e3 * t) * 3      # tín hiệu lệch 12 kHz
    iq += tone + (2 + 1j)                          # + DC offset
    iq = iq.real * 1.15 + 1j * iq.imag             # mất cân bằng biên độ
    stem = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "_iq_selftest")
    write_sigmf(stem, np.clip(iq.real, -32768, 32767) + 1j * np.clip(iq.imag, -32768, 32767),
                fs, fc, "ci16_le")
    h, dyn = read_iq_as_dyn(stem + ".sigmf-data", nchan=64)
    f = h["freqs_mhz"]
    k = int(np.argmax(dyn.mean(axis=1)))
    print(f"IQ: {h['ntime']} mẫu × {h['nchans']} kênh, tsamp {h['tsamp_s']*1e6:.1f} µs")
    print(f"đỉnh phổ tại {f[k]:.4f} MHz (kỳ vọng 1420.012) | "
          f"IQ fix: {h['iq_fix']}")
    ok = abs(f[k] - 1420.012) < 0.02
    print("SELFTEST IQ:", "PASS" if ok else "FAIL")
    for p in (stem + ".sigmf-data", stem + ".sigmf-meta"):
        os.unlink(p)
