# -*- coding: utf-8 -*-
"""
record_unattended.py — TRÌNH GHI TỰ ĐỘNG (không cần canh chừng) cho RTP-3.7.

Đúng yêu cầu: "thu thập dữ liệu mà không có mặt ở đó — channelize ngay thành
phổ động (dynamic spectrum) rồi mới ghi", 4–5 giờ mỗi phiên, tận dụng phần cứng
tối giản + bù phần mềm (psr_hw + psr_swcomp).

Đặc điểm:
    • Tự phát hiện SDR (RTL-SDR qua pyrtlsdr); KHÔNG có thiết bị → chế độ
      MÔ PHỎNG (replay từ psr_sim) để kiểm thử toàn chuỗi mà không cần phần cứng.
    • Channelize NGAY trên dòng IQ (FFT → nchan kênh, tích navg frame/lần ghi)
      → dung lượng ~0.25–0.6 MB/s thay vì 2.3 MB/s (IQ thô).
    • Ghi .fil TĂNG DẦN (fsync mỗi block) — mất điện chỉ mất block cuối.
    • ĐẾM MẪU + so với đồng hồ treo → phát hiện MẤT MẪU, ghi vào gap log.
    • Sidecar JSON: UTC, chuỗi phần cứng, ppm, cấu hình, thống kê RFI.
    • Dừng êm (Ctrl+C hoặc hết thời lượng), tổng kết cuối.

Cách dùng:
    python record_unattended.py --selftest               # test toàn chuỗi (mock)
    python record_unattended.py --mock --seconds 30      # ghi thử 30 s (mock)
    python record_unattended.py --target B0950+08 --hours 4.5 --band 423
    python record_unattended.py --target B0950+08 --hours 4.5 --band 423 --analyze
"""
from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import struct
import sys
import time
from datetime import datetime, timezone

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from psr_core import ensure_utf8_stdout
import ingest_guard as guard
import psr_paths as paths
import psr_hw

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = paths.data_dir()       # chính sách I/O tập trung


# ============================================================ nguồn dữ liệu
class RtlSource:
    """RTL-SDR thật (pyrtlsdr). Đếm mẫu để phát hiện mất mẫu."""

    def __init__(self, sample_rate: float, center_freq: float, gain: float):
        from rtlsdr import RtlSdr
        self.dev = RtlSdr()
        self.dev.sample_rate = sample_rate
        self.dev.center_freq = center_freq
        self.dev.gain = gain
        self.sample_rate = sample_rate
        self.center_freq = center_freq
        self.samples_read = 0
        self.gaps = []

    def read_iq(self, n: int) -> np.ndarray:
        x = self.dev.read_samples(n)
        self.samples_read += len(x)
        return np.asarray(x, dtype=np.complex64)

    def close(self):
        try:
            self.dev.close()
        except Exception:
            pass


class MockStream:
    """Mô phỏng phổ động TỪNG DÒNG (bộ nhớ O(nchan), không O(nchan×ntime)).

    Vì sao phải viết lại: bản cũ dùng psr_sim.simulate() sinh CẢ mảng —
    với mock 1.0 h × 64 kênh × 256 µs là 14 triệu dòng ≈ 3.6–7 GB RAM
    (đã gây lỗi thật khi bấm Dừng với giờ lớn). Bản này tính giải tích
    từng mẫu: mỗi dòng chỉ cần nhiễu + đóng góp của xung gần nhất.
    """

    def __init__(self, nchan: int, tsamp_s: float, n_rows: int, f_center_mhz: float,
                 bw_mhz: float, dm: float = 26.76, period_s: float = 0.253065,
                 w50_ms: float = 25.0, snr_target: float = 12.0, rfi: bool = True,
                 seed: int = 123, gap_every_s: float = 0.0):
        self.nchan = nchan
        self.tsamp = tsamp_s
        self.n_rows = n_rows
        self.period = period_s
        self.sigma_t = w50_ms * 1e-3 / 2.3548
        self.gaps = []
        self.i = 0
        self.samples_read = 0
        self.rng = np.random.default_rng(seed)

        # tần số từng kênh (SIGPROC: fch1 cao nhất, foff âm) → dùng trị tuyệt đối
        df = bw_mhz / nchan
        self.freqs = f_center_mhz + bw_mhz / 2 - df * (np.arange(nchan) + 0.5)
        fmax = float(self.freqs.max())
        self.delay = 4.148808e3 * dm * (1.0 / self.freqs**2 - 1.0 / fmax**2)

        duty = min(max(w50_ms * 1e-3 / period_s, 1e-4), 0.9)
        self.amp = snr_target / np.sqrt(nchan * n_rows * duty)

        self.rfi = rfi
        self.bad_ch: np.ndarray = np.array([], dtype=int)
        self.impulses: set = set()
        if rfi and nchan >= 8:
            self.bad_ch = self.rng.choice(nchan, size=max(1, nchan // 16),
                                          replace=False)
            self.bad_amp = self.rng.uniform(4.0, 12.0, size=len(self.bad_ch))
            n_imp = max(1, int(n_rows * tsamp_s / 30.0))
            self.impulses = set(self.rng.integers(0, n_rows, size=n_imp).tolist())
        self.gap_every_s = gap_every_s

    def next_row(self):
        if self.i >= self.n_rows:
            return None
        k = self.i
        t = k * self.tsamp
        row = 1.0 + self.rng.normal(0.0, 1.0, self.nchan)

        # xung gần nhất cho từng kênh (W ≪ P nên chỉ cần 1 xung)
        n_near = np.rint((t - self.delay) / self.period)
        t0 = n_near * self.period + self.delay
        z = (t - t0) / self.sigma_t
        near = np.abs(z) < 6.0
        if near.any():
            row[near] += self.amp * np.exp(-0.5 * z[near] ** 2)

        if self.rfi:
            if len(self.bad_ch):
                row[self.bad_ch] += self.bad_amp
            if k in self.impulses:
                row += self.rng.uniform(15.0, 40.0)

        self.i += 1
        self.samples_read += 1
        if self.gap_every_s > 0 and (k * self.tsamp) % self.gap_every_s < self.tsamp:
            skip = 3
            self.i += skip
            self.gaps.append(dict(row=self.i, skipped_rows=skip,
                                  t_rel_s=round(self.i * self.tsamp, 3)))
        return row

    def close(self):
        pass


class ReplaySource:
    """Mô phỏng: phát lại một dynamic spectrum đã sinh (psr_sim) theo dòng.

    Dùng khi KHÔNG có SDR: kiểm thử toàn bộ chuỗi ghi (header .fil, đếm mẫu,
    gap log, đọc lại) mà không cần phần cứng. Chú ý: bỏ qua bước channelize
    (nguồn đã ở mức phổ) — phần DSP đã được kiểm chứng riêng bằng selftest.
    """

    def __init__(self, dyn: np.ndarray, frame_period_s: float = 0.1,
                 realtime: bool = False, gap_every_s: float = 0.0):
        self.dyn = np.asarray(dyn)
        self.row_dt = frame_period_s
        self.realtime = realtime
        self.gap_every_s = gap_every_s
        self.i = 0
        self.samples_read = 0
        self.gaps = []
        self._t0 = time.monotonic()

    def next_row(self):
        if self.i >= self.dyn.shape[1]:
            return None
        row = self.dyn[:, self.i]
        self.i += 1
        self.samples_read += 1
        if self.gap_every_s > 0:
            # mô phỏng mất mẫu: nhảy cóc + ghi gap
            if (self.i * self.row_dt) % self.gap_every_s < self.row_dt:
                skip = 3
                self.i += skip
                self.gaps.append(dict(row=self.i, skipped_rows=skip,
                                      t_rel_s=round(self.i * self.row_dt, 3)))
        if self.realtime:
            target = self._t0 + self.i * self.row_dt
            dt = target - time.monotonic()
            if dt > 0:
                time.sleep(dt)
        return row

    def close(self):
        pass


# ============================================================ ghi .fil tăng dần
class FilWriter:
    """Ghi SIGPROC .fil theo dòng (uint8), header trước, rows nối tiếp."""

    def __init__(self, path: str, nchan: int, tsamp_s: float, fch1: float,
                 foff: float, source_name: str, tstart_mjd: float):
        self.path = path
        self.nchan = nchan
        self.fh = open(path, "wb")
        s = lambda t: self.fh.write(struct.pack("<i", len(t.encode())) + t.encode())
        s("HEADER_START")
        s("source_name"); s(source_name)
        for k, v in (("nbits", 8), ("nchans", nchan), ("nifs", 1),
                     ("nbeams", 1), ("machine_id", 99), ("telescope_id", 99),
                     ("data_type", 1), ("bary", 0), ("signed", 0)):
            s(k); self.fh.write(struct.pack("<i", int(v)))
        for k, v in (("tsamp", tsamp_s), ("tstart", tstart_mjd),
                     ("fch1", fch1), ("foff", foff), ("refdm", 0.0)):
            s(k); self.fh.write(struct.pack("<d", float(v)))
        s("HEADER_END")
        self.rows = 0
        self._scale = None

    def write_row(self, power: np.ndarray, clip_lo=1, clip_hi=250):
        """power: float array (nchan,) — chuẩn hoá trung bình về ~100 rồi ghi uint8."""
        p = np.asarray(power, dtype=np.float64)
        if self._scale is None:
            med = np.median(p) + 1e-12
            self._scale = 100.0 / med
        q = np.clip(p * self._scale, clip_lo, clip_hi)
        self.fh.write(q.astype(np.uint8).tobytes())
        self.rows += 1
        if self.rows % 512 == 0:
            self.fh.flush()
            os.fsync(self.fh.fileno())

    def close(self):
        self.fh.flush(); os.fsync(self.fh.fileno()); self.fh.close()


# ============================================================ channelize
class ChanStream:
    """Biến dòng IQ thành dòng phổ: FFT nchan mẫu → tích navg frame → 1 row."""

    def __init__(self, nchan: int, navg: int):
        self.nchan = nchan
        self.navg = navg
        self.acc = np.zeros(nchan)
        self.k = 0

    def push(self, iq: np.ndarray) -> list[np.ndarray]:
        out = []
        n = len(iq) // self.nchan
        x = iq[: n * self.nchan].reshape(n, self.nchan)
        spec = np.fft.fftshift(np.fft.fft(x, axis=1), axes=1)
        p = (np.abs(spec) ** 2).sum(axis=0)
        self.acc += p
        self.k += 1
        if self.k >= self.navg:
            out.append(self.acc / self.k)
            self.acc = np.zeros(self.nchan)
            self.k = 0
        return out


# ============================================================ phiên ghi
def run_session(target: str = "B0950+08", hours: float = 4.5, band: str = "423",
                out_dir: str | None = None, mock: bool | None = None,
                seconds: float | None = None, analyze: bool = False,
                nchan: int = 64, tsamp_us: float = 256.0,
                gain_db: float | None = None, gap_every_s: float = 0.0,
                stop_event=None, source: str | None = None,
                reconnect_tries: int = 8) -> dict:
    """Ghi một phiên. `source`: "auto" | "mock" | "real".

    - auto (mặc định): dò SDR — có thì thu THẬT, không có thì MÔ PHỎNG (kèm
      cảnh báo trong metadata: mode = "fallback-mock").
    - mock: bắt buộc mô phỏng (để thử pipeline, không cần rút cáp SDR).
    - real: BẮT BUỘC SDR thật. Không có / mất kết nối giữa phiên → BÁO LỖI và
      dừng, TUYỆT ĐỐI không âm thầm ghi dữ liệu mô phỏng giả (một phiên 4–5 h
      sẽ bị hỏng mà không ai biết). Tự thử kết nối lại `reconnect_tries` lần.
    """
    if source is None:
        # tương thích API cũ: mock=True → mô phỏng; mock=False/None → "Tự động"
        # (chế độ nghiêm ngặt phải chỉ định rõ source="real")
        source = "mock" if mock else "auto"
    source = str(source).lower()
    if source not in ("auto", "mock", "real"):
        raise ValueError(f"source phải là auto/mock/real, nhận '{source}'")
    chain = psr_hw.detect_chain(band, goal="unattended")
    print(chain.summary())
    dur = seconds if seconds else hours * 3600.0

    out_dir = out_dir or os.path.join(DATA, datetime.now().strftime("%Y%m%dT%H%M%S"))
    os.makedirs(out_dir, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = os.path.join(out_dir, f"{target.replace('+','p').replace('-','m')}_{stamp}.fil")

    # ---- cấu hình kênh (băng thông SDR → fch1/foff)
    bw = chain.bw_mhz
    fc = chain.band_mhz
    fch1 = fc + bw / 2.0            # SIGPROC: kênh đầu = tần số cao nhất
    foff = -bw / nchan
    gain = gain_db if gain_db is not None else min(chain.gain_db, 40.0)

    # ---- Q2: kiểm tra ổ đĩa TRƯỚC khi ghi (ước lượng ×1,2)
    est_bytes = nchan * (dur / (tsamp_us * 1e-6)) * 1.0    # 1 byte/mẫu (uint8)
    _pf = guard.disk_preflight(out_dir, est_bytes)
    print(f"→ Q2 đĩa: cần {_pf['need']/1e9:.1f} GB (gồm 20 % dự phòng), "
          f"còn trống {_pf['free']/1e9:.1f} GB")
    if not _pf["ok"]:
        raise RuntimeError(
            f"không đủ dung lượng: cần {_pf['need']/1e9:.1f} GB, chỉ còn "
            f"{_pf['free']/1e9:.1f} GB (giữ chỗ tối thiểu "
            f"{_pf['min_free_mb']} MB). Dừng TRƯỚC khi tạo file.")
    meta = dict(target=target, band_mhz=fc, nchan=nchan, tsamp_s=tsamp_us * 1e-6,
                bw_mhz=bw, gain_db=gain, chain=chain.parts,
                fallbacks=chain.fallbacks, tsys_k=round(chain.t_sys_k, 1),
                sefd_jy=round(chain.sefd_jy), started_utc=stamp,
                mode="mock-replay" if mock else "sdr", gaps=[])

    t_wall0 = time.monotonic()
    rows_expected = 0
    MOCK_CAP_S = 180.0          # giới hạn mô phỏng (RAM/thời gian)
    meta["fallback"] = None
    meta["source_requested"] = source
    probe = psr_hw.probe_sdr()
    meta["sdr_probe"] = {k: probe.get(k) for k in
                         ("found", "name", "tuner", "serial", "n_devices", "error")}
    print(f"→ Nguồn yêu cầu: {source.upper()} | dò SDR: "
          + (f"THẤY {probe['name']}"
             + (f" ({probe['tuner']})" if probe.get('tuner') else "")
             if probe["found"] else f"KHÔNG THẤY ({probe.get('error')})"))
    if source == "real" and not probe["found"]:
        shutil.rmtree(out_dir, ignore_errors=True) if False else None
        raise RuntimeError(
            "Không tìm thấy RTL-SDR nhưng đang ở chế độ BẮT BUỘC SDR thật: "
            + str(probe.get("error") or "không rõ lý do")
            + ". Cắm lại thiết bị / kiểm tra driver, hoặc đổi sang 'Tự động'.")

    def _start_mock(reason: str):
        """Khởi động nguồn mô phỏng (dùng trực tiếp, hoặc khi KHÔNG có SDR)."""
        dur_mock = min(dur, MOCK_CAP_S)
        n_rows = max(1, int(dur_mock / (tsamp_us * 1e-6)))
        if dur_mock < dur:
            print(f"→ MÔ PHỎNG: giới hạn {dur_mock:.0f} s (yêu cầu {dur:.0f} s)"
                  f" — dùng SDR thật để ghi dài.")
        src = MockStream(nchan=nchan, tsamp_s=tsamp_us * 1e-6, n_rows=n_rows,
                         f_center_mhz=fc, bw_mhz=bw, dm=26.76,
                         period_s=0.253065, w50_ms=25.0, snr_target=12.0,
                         rfi=True, gap_every_s=gap_every_s)
        wr = FilWriter(path, nchan, tsamp_us * 1e-6, fch1, foff, target, 60000.0)
        print(f"→ MOCK (streaming): {n_rows} dòng, {nchan} kênh → {path}")
        if reason:
            print(f"   ⚠ lý do chuyển mô phỏng: {reason}")
        return src, wr

    src = wr = None
    use_mock = (source == "mock") or (source == "auto" and not probe["found"])
    try:
        if use_mock:
            _reason = ("" if source == "mock" else
                       f"tự động: {probe.get('error') or 'không có SDR'}")
            if source == "auto":
                meta["fallback"] = _reason     # ghi rõ vì sao phải mô phỏng
            src, wr = _start_mock(_reason)
            meta["mode"] = "mock" if source == "mock" else "fallback-mock"
            while True:
                if stop_event is not None and stop_event.is_set():
                    print("→ dừng bởi lệnh DỪNG")
                    break
                row = src.next_row()
                if row is None:
                    break
                wr.write_row(row)
                rows_expected += 1
            meta["gaps"] = src.gaps
        else:
            # ---- THU THẬT. Chế độ "real": lỗi là LỖI, không được giả lập.
            try:
                src = RtlSource(2.4e6, fc * 1e6, gain)
            except Exception as e:
                reason = f"không mở được SDR ({type(e).__name__}: {e})"
                if source == "real":
                    raise RuntimeError(
                        "Đang ở chế độ BẮT BUỘC SDR thật nhưng không mở được "
                        f"thiết bị: {reason}. KHÔNG ghi dữ liệu mô phỏng thay thế.")
                meta["fallback"] = reason
                print(f"→ KHÔNG CÓ SDR: {reason}")
                print("→ TỰ ĐỘNG CHUYỂN SANG CHẾ ĐỘ MÔ PHỎNG (vẫn ghi "
                      "đúng định dạng để kiểm chứng chuỗi)")
                src.close() if src is not None else None
                src, wr = _start_mock(reason)
                meta["mode"] = "fallback-mock"
                while True:
                    if stop_event is not None and stop_event.is_set():
                        print("→ dừng bởi lệnh DỪNG")
                        break
                    row = src.next_row()
                    if row is None:
                        break
                    wr.write_row(row)
                    rows_expected += 1
                meta["gaps"] = src.gaps
            else:
                meta["mode"] = "sdr"
                cs = ChanStream(nchan, navg=max(
                    1, int(round(2.4e6 * tsamp_us * 1e-6 / nchan))))
                wr = FilWriter(path, nchan, tsamp_us * 1e-6, fch1, foff,
                               target, 60000.0)
                block = 2 ** 18
                print(f"→ SDR THẬT: {target} @ {fc} MHz, {dur/3600:.2f} h, "
                      f"{nchan} kênh × {tsamp_us:.0f} µs → {path}")
                last_beat = time.monotonic()
                while time.monotonic() - t_wall0 < dur:
                    if stop_event is not None and stop_event.is_set():
                        print("→ dừng bởi lệnh DỪNG — đóng file an toàn")
                        break
                    try:
                        iq = src.read_iq(block)
                    except Exception as e:
                        # USB lỏng / rớt driver giữa đêm: KHÔNG được tạo dữ liệu giả
                        err = f"{type(e).__name__}: {e}"
                        meta.setdefault("sdr_errors", []).append(
                            dict(t_rel_s=round(time.monotonic() - t_wall0, 1),
                                 error=err))
                        print(f"   ⚠ MẤT SDR: {err} — thử kết nối lại…")
                        ok = False
                        for k in range(1, reconnect_tries + 1):
                            time.sleep(min(2.0 * k, 10.0))
                            if stop_event is not None and stop_event.is_set():
                                break
                            try:
                                src.close()
                            except Exception:
                                pass
                            try:
                                src = RtlSource(2.4e6, fc * 1e6, gain)
                                print(f"   ✓ kết nối lại được (lần {k})")
                                ok = True
                                break
                            except Exception as e2:
                                print(f"      lần {k}/{reconnect_tries}: {e2}")
                        if not ok:
                            if source == "real":
                                meta["aborted"] = "mất SDR, không kết nối lại được"
                                meta["error"] = err
                                print("→ DỪNG PHIÊN: chế độ BẮT BUỘC SDR thật nên "
                                      "không chuyển sang mô phỏng. Dữ liệu đã ghi "
                                      "được giữ nguyên.")
                                break
                            meta["fallback"] = f"mất SDR giữa phiên: {err}"
                            print("→ chế độ Tự động: chuyển tiếp sang MÔ PHỎNG")
                            src, _wr2 = _start_mock(err)
                            wr = _wr2
                            meta["mode"] = "fallback-mock"
                            continue
                        continue
                    for row in cs.push(iq):
                        wr.write_row(row)
                        rows_expected += 1
                    # phát hiện mất mẫu: số mẫu kỳ vọng vs thực đọc
                    dt = time.monotonic() - t_wall0
                    expect = int(dt * src.sample_rate)
                    if expect - src.samples_read > src.sample_rate * 0.05:
                        src.gaps.append(dict(t_rel_s=round(dt, 2),
                                             missing=int(expect - src.samples_read)))
                        src.samples_read = expect      # đặt lại mốc
                    if time.monotonic() - last_beat > 60:
                        last_beat = time.monotonic()
                        print(f"   [{(dt/3600):.2f} h] {wr.rows} dòng, "
                              f"{len(src.gaps)} gap, "
                              f"{os.path.getsize(path)/1e6:.0f} MB")
                        _free = shutil.disk_usage(out_dir).free
                        if _free < 200 * 1024 * 1024:
                            meta["aborted"] = "disk_full"
                            print(f"→ DỪNG: ổ đĩa còn {_free/1e6:.0f} MB")
                            break
                meta["gaps"] = src.gaps
        if wr is not None:
            wr.close()
        if src is not None:
            src.close()
    except KeyboardInterrupt:
        print("\n→ dừng bởi người dùng — đóng file an toàn")
        for o in (wr, src):
            try:
                if o is not None:
                    o.close()
            except Exception:
                pass

    meta["rows"] = rows_expected
    meta["duration_s"] = round(rows_expected * tsamp_us * 1e-6, 3)
    meta["wall_s"] = round(time.monotonic() - t_wall0, 1)
    meta["file_bytes"] = os.path.getsize(path)
    meta["n_gaps"] = len(meta["gaps"])
    meta["rate_kbps"] = round(nchan / (tsamp_us * 1e-6) / 125.0, 1)

    print(f"\n→ {rows_expected} dòng ({meta['duration_s']} s dữ liệu), "
          f"{meta['file_bytes']/1e6:.1f} MB, {meta['rate_kbps']} kbps, "
          f"{meta['n_gaps']} gap")

    # ---- kiểm chứng: đọc lại file vừa ghi (PHẢI trước khi ghi sidecar)
    from psr_fil import read_fil
    h, dyn = read_fil(path, validate=True)
    ok = (h["nchans"] == nchan and h["ntime"] == rows_expected
          and abs(h["tsamp"] - tsamp_us * 1e-6) < 1e-12)
    meta["roundtrip_ok"] = bool(ok)
    meta["roundtrip_nchans"] = int(h["nchans"])
    meta["roundtrip_ntime"] = int(h["ntime"])
    print(f"→ kiểm chứng đọc lại: {'PASS' if ok else 'FAIL'} "
          f"({h['ntime']} dòng × {h['nchans']} kênh)")

    # sidecar ghi SAU khi đã có roundtrip_ok (trước đây ghi sớm → thiếu khóa)
    side = path.replace(".fil", ".json")
    meta["input_sha256"] = guard.input_fingerprint(path).get("sha256_head")
    meta["schema_version"] = 3
    meta["disk"] = _pf
    guard.atomic_write_json(side, meta)       # Q2: ghi nguyên tử
    print(f"→ metadata: {side}")

    if analyze:
        import psr_detect
        print("\n→ chạy pipeline phát hiện trên dữ liệu vừa ghi...")
        psr_detect.detect(path, dm_ref=26.76, p_ref=0.253065)
    return meta


def selftest() -> bool:
    """Test toàn chuỗi ghi + đọc lại + phát hiện mất mẫu (không cần SDR)."""
    print("=== SELFTEST trình ghi tự động (mock, 12 s dữ liệu) ===")
    m = run_session(target="B0950+08", seconds=12.0, band="423", mock=True,
                    gap_every_s=4.0, out_dir=os.path.join(DATA, "_selftest"))
    ok = (m["roundtrip_ok"] and m["rows"] > 1000)
    print(f"\nrows={m['rows']} gaps={m['n_gaps']} roundtrip={m['roundtrip_ok']}")
    print(f"SELFTEST: {'PASS' if ok else 'FAIL'}")
    return ok


if __name__ == "__main__":
    ensure_utf8_stdout()
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--mock", action="store_true")
    ap.add_argument("--target", default="B0950+08")
    ap.add_argument("--hours", type=float, default=4.5)
    ap.add_argument("--seconds", type=float, default=None)
    ap.add_argument("--band", default="423")
    ap.add_argument("--out", default=None)
    ap.add_argument("--analyze", action="store_true")
    ap.add_argument("--nchan", type=int, default=64)
    ap.add_argument("--tsamp-us", type=float, default=256.0)
    ap.add_argument("--gain", type=float, default=None)
    ap.add_argument("--gap-every", type=float, default=0.0)
    a = ap.parse_args()
    if a.selftest:
        sys.exit(0 if selftest() else 1)
    run_session(target=a.target, hours=a.hours, band=a.band, out_dir=a.out,
                mock=a.mock, seconds=a.seconds, analyze=a.analyze,
                nchan=a.nchan, tsamp_us=a.tsamp_us, gain_db=a.gain,
                gap_every_s=a.gap_every)
