# -*- coding: utf-8 -*-
"""
psr_fits.py — Đọc PSRFITS (định dạng chuẩn của Parkes/GBT/FAST/Arecibo) + ghi
file PSRFITS tối thiểu để tự kiểm thử.

Vì sao cần: corpus dữ liệu "xấu" (data/stress/) có file PSRFITS hỏng thật
(`empty.fits` có NAXIS2 = 0; `test_4pol.fits` thiếu NPOL/NCHAN). Người dùng sẽ
gặp cả hai kiểu: file hợp lệ và file hỏng. Module này:
    * đọc được PSRFITS hợp lệ (nhiều SUBINT, 1–4 phân cực, DAT_SCL/DAT_OFFS)
    * với file hỏng → ném lỗi CÓ NỘI DUNG (nói rõ thiếu khoá nào / rỗng / cụt)
    * `write_psrfits()` sinh file hợp lệ để kiểm chứng đường đọc

Bố cục PSRFITS chuẩn:
    HDU0  PRIMARY : OBSFREQ, OBSBW, OBSNCHAN, NPOL, TBIN, STT_IMJD, STT_SMJD,
                    STT_OFFS, TELESCOP, SRC_NAME, POL_TYPE
    HDU1+ SUBINT  : NAXIS2 = số subint; cột DATA (nsblk×nchan×npol),
                    DAT_FREQ (MHz), DAT_OFFS, DAT_SCL, TSUBINT, OFFS_SUB
"""
from __future__ import annotations

import numpy as np

def _num(v, default=None):
    """Đọc số từ header FITS, chịu được placeholder '*', 'UNSET', ''."""
    if v is None:
        return default
    if isinstance(v, (int, float)):
        return float(v)
    t = str(v).strip()
    if t in ("", "*", "UNSET", "NONE", "None", "null"):
        return default
    try:
        return float(t)
    except ValueError:
        return default


_REQUIRED = ("OBSFREQ", "OBSBW", "OBSNCHAN")   # NPOL/TBIN có thể nằm ở SUBINT


def read_psrfits(path: str, max_seconds: float | None = None,
                 pol: int | str = "sum", strict: bool = False):
    """Đọc PSRFITS → (header chuẩn hoá, dyn (nchan, ntime) float32).

    Ném ValueError với thông điệp rõ ràng nếu file hỏng/rỗng/thiếu khoá.
    """
    try:
        from astropy.io import fits
    except Exception as e:                        # pragma: no cover
        raise RuntimeError("cần astropy để đọc PSRFITS") from e

    warns: list[str] = []
    with fits.open(path, memmap=True) as hdus:
        ph = hdus[0].header
        missing = [k for k in _REQUIRED if k not in ph]
        if missing:
            raise ValueError(
                f"PSRFITS thiếu khoá bắt buộc: {', '.join(missing)} "
                f"(file có {len(ph)} khoá; đây là file test/hỏng)")
        nchan = int(_num(ph.get("OBSNCHAN"), 0) or 0)
        # TBIN có thể ở PRIMARY hoặc ở SUBINT (nhiều file thật đặt ở SUBINT)
        sub_hdrs = [h.header for h in hdus[1:]]
        tbin = _num(ph.get("TBIN"), 0.0) or 0.0
        if not tbin:
            for sh in sub_hdrs:
                if sh.get("TBIN"):
                    tbin = _num(sh.get("TBIN"), 0.0) or 0.0; break
        npol = int(_num(ph.get("NPOL"), 0) or 0)
        f_center = _num(ph.get("OBSFREQ"), 0.0) or 0.0
        bw = _num(ph.get("OBSBW"), 0.0) or 0.0                 # có thể âm (đảo thứ tự kênh)
        src = str(ph.get("SRC_NAME", "?")).strip()
        if tbin <= 0:
            raise ValueError("TBIN = 0 hoặc thiếu ở cả PRIMARY và SUBINT "
                             "→ không xác định được thời gian mẫu")
        if nchan < 1:
            raise ValueError(f"OBSNCHAN = {nchan} không hợp lệ")
        if bw == 0:
            raise ValueError("OBSBW = 0 → không xác định được tần số kênh")

        subs = [h for h in hdus[1:] if h.header.get("NAXIS2") is not None
                and h.header.get("NAXIS2", 0) > 0
                and "DATA" in (h.columns.names if h.columns else [])]
        if not subs:
            n_all = sum(int(_num(h.header.get("NAXIS2"), 0) or 0) for h in hdus[1:])
            raise ValueError(
                f"PSRFITS không có dữ liệu: tổng số subint = {n_all} "
                f"(NAXIS2 = 0 nghĩa là file rỗng)")

        # ưu tiên NCHAN/NPOL khai báo trong SUBINT (OBSNCHAN là số kênh GỐC
        # trước khi dedisperse on-line, không phải số kênh lưu trong DATA)
        _h0 = subs[0].header
        _nsub_ch = _num(_h0.get("NCHAN"), None)
        _nsub_pol = _num(_h0.get("NPOL"), None)
        if _nsub_ch and int(_nsub_ch) > 0 and int(_nsub_ch) != nchan:
            warns.append(f"NCHAN(SUBINT)={int(_nsub_ch)} khác OBSNCHAN={nchan} "
                         f"→ dùng NCHAN")
            nchan = int(_nsub_ch)
        if _nsub_pol and int(_nsub_pol) > 0:
            npol = int(_nsub_pol)

        if npol < 1:
            # suy NPOL = len(DATA)/(nsblk*nchan); nếu lẻ → coi như 1
            hdu0 = subs[0]
            n_el = int(np.asarray(hdu0.data["DATA"][0]).size)
            nsblk0 = int(_num(hdu0.header.get("NSBLK"), 1) or 1)
            guess = n_el / float(nsblk0 * nchan)
            npol = int(round(guess)) if guess >= 0.9 else 1
            warns.append(f"thiếu khoá NPOL → suy ra NPOL = {npol} "
                         f"từ kích thước DATA ({n_el} phần tử)")

        chunks, freqs, t_total = [], None, 0.0
        for hdu in subs:
            d = hdu.data
            nsub = len(d)
            _nch_sub = _num(hdu.header.get("NCHAN"), None)
            if _nch_sub and int(_nch_sub) > 0 and int(_nch_sub) != nchan:
                warns.append(f"NCHAN(SUBINT)={int(_nch_sub)} khác OBSNCHAN={nchan} "
                             f"→ dùng NCHAN (OBSNCHAN là số kênh gốc trước "
                             f"dedisperse on-line)")
                nchan = int(_nch_sub)
                freqs = None
            nsblk = int(_num(hdu.header.get("NSBLK"), 0) or 0) or None
            if nsblk is None:
                # NSBLK='*' hoặc thiếu → suy từ số phần tử DATA
                _el = int(np.asarray(d["DATA"][0]).size)
                if _el and nchan and npol:
                    nsblk = max(1, _el // (nchan * npol))
                    warns.append(f"NSBLK thiếu/không hợp lệ → suy ra {nsblk} "
                                 f"từ kích thước DATA ({_el} phần tử)")
            if freqs is None:
                df = np.asarray(d["DAT_FREQ"][0], dtype=float)
                if df.size == nchan:
                    freqs = df
                    warns.append("tần số kênh lấy từ DAT_FREQ")
                else:
                    # suy từ OBSFREQ/OBSBW: kênh 0 = f_center + bw/2
                    freqs = f_center + bw / 2 - (np.arange(nchan) + 0.5) * (
                        bw / nchan)
                    warns.append("DAT_FREQ không khớp nchan → suy từ "
                                 "OBSFREQ/OBSBW")
            for i in range(nsub):
                raw = np.asarray(d["DATA"][i])
                scl = np.asarray(d["DAT_SCL"][i], dtype=float)
                off = np.asarray(d["DAT_OFFS"][i], dtype=float)
                td = hdu.header.get("TDIM%d" % _data_colnum(hdu), None)
                shape = _parse_tdim(td, nsblk, nchan, npol)
                if shape[2] != nchan and int(np.prod(shape)) == np.asarray(raw).size:
                    # TDIM mô tả ĐÚNG cách dữ liệu được lưu → tin TDIM hơn NCHAN
                    warns.append(f"NCHAN={nchan} không khớp TDIM {td} → dùng "
                                 f"{shape[2]} kênh theo TDIM")
                    nchan = int(shape[2])
                    freqs = f_center + bw / 2 - (np.arange(nchan) + 0.5) * (bw / nchan)
                arr = raw.reshape(shape).astype(np.float64)
                # arr: (nsblk, npol, nchan) theo TDIM chuẩn
                if scl.size == npol * nchan:
                    s = scl.reshape(npol, nchan)[None, :, :]
                    o = off.reshape(npol, nchan)[None, :, :]
                    arr = arr * s + o
                elif scl.size:
                    arr = arr * scl.ravel()[0] + off.ravel()[0]
                else:
                    warns.append("thiếu DAT_SCL/DAT_OFFS → dùng giá trị thô")
                chunks.append(arr)
                t_total += int(_num(hdu.header.get("NSBLK"), shape[0]) or shape[0])
                if max_seconds is not None and t_total * tbin >= max_seconds:
                    break
            if max_seconds is not None and t_total * tbin >= max_seconds:
                break

    cube = np.concatenate(chunks, axis=0)          # (ntime, npol, nchan)
    if max_seconds is not None:
        keep = min(cube.shape[0], int(max_seconds / tbin))
        cube = cube[:keep]
    if npol > 1:
        if pol == "sum":
            dyn = cube.sum(axis=1).T
            warns.append(f"NPOL = {npol}: đã CỘNG các phân cực (Stokes I xấp xỉ)")
        elif pol == "first":
            dyn = cube[:, 0, :].T
        elif isinstance(pol, int) and 0 <= pol < npol:
            dyn = cube[:, pol, :].T
        else:
            raise ValueError(f"pol = {pol!r} không hợp lệ (NPOL = {npol})")
    else:
        dyn = cube[:, 0, :].T
    dyn = np.ascontiguousarray(dyn, dtype=np.float32)
    if dyn.size == 0:
        raise ValueError("không đọc được mẫu nào")

    h = dict(
        source=src, freqs_mhz=freqs, tsamp_s=tbin, nchans=nchan, nifs=npol,
        ntime=int(dyn.shape[1]), t_s=float(dyn.shape[1] * tbin), nbits=0,
        data_offset=0, data_file_bytes=0, read_warnings=warns,
        telescope=str(ph.get("TELESCOP", "?")).strip(),
        polarisation=str(ph.get("POL_TYPE", "?")).strip())
    h["validation"] = _validate(dyn, h)
    if strict and not h["validation"]["ok"]:
        raise ValueError("PSRFITS không đạt kiểm chứng: "
                         + "; ".join(h["validation"]["problems"]))
    return h, dyn


def _parse_tdim(tdim, nsblk, nchan, npol):
    """TDIMx = '(nchan,npol,nsblk)' → shape (nsblk, npol, nchan); mặc định vậy."""
    if isinstance(tdim, str):
        try:
            dims = [int(x) for x in tdim.strip("()").split(",")]
            if len(dims) == 3:
                # TDIM ghi theo thứ tự nhanh→chậm của FITS: (nchan, npol, nsblk)
                return (dims[2], dims[1], dims[0])
        except Exception:
            pass
    if nsblk is None:
        try:
            size = int(np.prod([d for d in (1,)]) or 1)
        except Exception:
            size = 1
    return (nsblk or 1, npol, nchan)


def _data_colnum(hdu):
    try:
        return list(hdu.columns.names).index("DATA") + 1
    except Exception:
        return 1


def _validate(dyn, h):
    fs = np.asarray(dyn, dtype=np.float64)
    problems, warnings = [], []
    if fs.size == 0:
        problems.append("mảng rỗng")
        return {"ok": False, "problems": problems, "warnings": warnings,
                "stats": {}}
    if not np.isfinite(fs).all():
        problems.append("có NaN/Inf")
    if float(fs.std()) == 0.0:
        problems.append("dữ liệu phẳng (một giá trị)")
    stats = dict(mean=float(fs.mean()), std=float(fs.std()),
                 tmin=float(fs.min()), tmax=float(fs.max()),
                 nchan=int(fs.shape[0]), ntime=int(fs.shape[1]))
    return {"ok": not problems, "problems": problems,
            "warnings": warnings, "stats": stats}


# ------------------------------------------------------------------ ghi
def write_psrfits(path: str, dyn: np.ndarray, *, tsamp_s: float,
                  f_center_mhz: float, bw_mhz: float, source: str = "TEST",
                  telescope: str = "TNU", npol: int = 1):
    """Ghi PSRFITS TỐI GIẢN hợp lệ (1–4 pol, 1 subint) để tự kiểm thử.

    dyn: (nchan, ntime) hoặc (npol, nchan, ntime) nếu npol>1.
    """
    from astropy.io import fits
    dyn = np.asarray(dyn, dtype=np.float32)
    if npol == 1:
        cube = dyn[None, :, :]                     # (1, nchan, ntime)
    else:
        cube = dyn
    nchan, ntime = cube.shape[1], cube.shape[2]
    nsblk = ntime
    # FITS "I" = int16 CÓ DẤU (32768 sẽ bị wrap thành -32768 — lỗi đã gặp).
    # Ghi thẳng int16 với thang 0.125, offset 0 → tái tạo đúng dyn.
    data16 = np.clip(np.rint(cube.transpose(2, 0, 1) * 8),
                     -32768, 32767).astype(np.int16)   # (ntime, npol, nchan)
    freqs = (f_center_mhz + bw_mhz / 2
             - (np.arange(nchan) + 0.5) * (bw_mhz / nchan))
    scl = np.full((1, npol * nchan), 0.125, dtype=np.float32)
    offs = np.zeros((1, npol * nchan), dtype=np.float32)
    ph = fits.PrimaryHDU()
    ph.header.update(dict(
        OBSFREQ=f_center_mhz, OBSBW=bw_mhz, OBSNCHAN=nchan, NPOL=npol,
        TBIN=tsamp_s, TELESCOP=telescope, SRC_NAME=source,
        POL_TYPE="AABBCRCI" if npol == 4 else ("AA" if npol == 2 else "INTEN"),
        STT_IMJD=60000, STT_SMJD=0, STT_OFFS=0.0, OBSERVER="selftest"))
    c = fits.Column(name="DATA", format=f"{nchan * npol * nsblk}I",
                    dim=f"({nchan},{npol},{nsblk})",
                    array=data16.reshape(1, nchan * npol * nsblk))
    c2 = fits.Column(name="DAT_FREQ", format=f"{nchan}E", unit="MHz",
                     array=np.repeat(freqs[None, :], 1, axis=0))
    c3 = fits.Column(name="DAT_WTS", format=f"{nchan}E",
                     array=np.ones((1, nchan), dtype=np.float32))
    c4 = fits.Column(name="DAT_OFFS", format=f"{npol*nchan}E", array=offs)
    c5 = fits.Column(name="DAT_SCL", format=f"{npol*nchan}E", array=scl)
    c6 = fits.Column(name="TSUBINT", format="1D", array=[nsblk * tsamp_s])
    c7 = fits.Column(name="OFFS_SUB", format="1D", array=[0.0])
    sh = fits.BinTableHDU.from_columns([c, c2, c3, c4, c5, c6, c7])
    sh.header["NSBLK"] = nsblk
    sh.header["NSUB"] = 1
    sh.header["TBIN"] = tsamp_s
    fits.HDUList([ph, sh]).writeto(path, overwrite=True)
    return path


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    import tempfile, os
    rng = np.random.default_rng(0)
    d = rng.normal(100, 10, (64, 2000)).astype(np.float32)
    d[20:40, 1000:1020] += 200                      # "xung" để kiểm tra
    fd, p = tempfile.mkstemp(suffix=".fits"); os.close(fd)
    write_psrfits(p, d, tsamp_s=2.5e-4, f_center_mhz=1420.0, bw_mhz=10.0)
    h, d2 = read_psrfits(p, strict=True)
    err = float(np.max(np.abs(d2 - d)))
    print(f"write→read: shape {d2.shape} (gốc {d.shape}), "
          f"sai số lượng tử lớn nhất {err:.1f} đơn vị ADC")
    print(f"tần số: {h['freqs_mhz'].min():.1f}–{h['freqs_mhz'].max():.1f} MHz, "
          f"tsamp {h['tsamp_s']*1e6:.0f} µs, ntime {h['ntime']}")
    os.unlink(p)
    print("SELFTEST PSRFITS:", "PASS" if d2.shape == d.shape else "FAIL")
