# B0329+54 — mẫu kiểm chứng

File: `data/B0329+54.fil` (2,10 s, 4096 kênh, 960–1920 MHz, tsamp 256 µs). Header `source=TEMP`, provenance **chưa xác minh**.

## Số liệu chạy thật gần nhất
Lệnh: `psr_detect.py --file ../data/B0329+54.fil --dm-ref 26.7 --p 0.714519`

- Xung mạnh nhất: t = 1722.9 ms, SNR 608,4σ, W50 6,8 ms.
- Xung thứ hai: t = 291.6 ms, SNR 593,4σ.
- Xung thứ ba: t = 1006.3 ms, SNR 418,1σ.
- DM boxcar (dm_best): 27,25 pc cm⁻³.
- DM subband Theil–Sen: 26,32 ± 0,79 pc cm⁻³ (jackknife, 8 subband, có sàn hệ thống 3%).
- Điểm tần thấp 1019,9 MHz lệch ~7,1 ms; nguyên nhân chưa xác định.
- Kiểm chứng: pha mod P khớp (292,4 ± 1,0 ms); đối chứng nền SNR 9,2 (< 12).

## Lưu ý
- DM boxcar và DM subband là hai phép đo khác nhau. Không ép thành một số.
- Không báo "17σ" với 8 subband.
- Với ~2 s dữ liệu, không có fold tại P (file < 5×P).

Liên quan: [[Pipeline phát hiện pulsar]], [[Quy ước hình vẽ]].
