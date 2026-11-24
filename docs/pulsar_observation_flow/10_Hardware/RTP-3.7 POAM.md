# POAM RTP-3.7 — tóm tắt phần cứng

Nguồn đầy đủ: `docs/09_ho_so_thiet_bi_rtp37.md`. Ghi chú này chỉ tóm tắt; khi có số mới, cập nhật file gốc trước.

## Chảo và trạm
- Đường kính 3,7 m, η ≈ 0,55, A_eff ≈ 5,91 m² `[TÍNH]`.
- Mount El/Az, jackscrew cho EL, resolver và công tắc hành trình. AZ 0–360°, EL 0–90° `[DS]`.
- Trạm TP.HCM, vĩ độ ≈ 10,78° N. Toạ độ trong RTCS đang nhập 106,79°E / 10,76°N, khác toạ độ hồ sơ 106,7009°E. Lệch ~0,09° kinh độ → pointing lệch ~0,9° ở 4 GHz `[ẢNH]`/`[TÍNH]`.

## Front-end
- Hộp tiêu điểm ghi **C-Band**. L-band feed là phụ kiện rời, **chưa xác nhận đã lắp** `[ẢNH]`.
- LO của LNB chưa đọc được `[?]`.

## Receiver
- Dải 100 MHz – 6 GHz, băng tức thời tối đa 50 MHz, gain 0–70 dB `[DS]`.
- IQ tối đa 15 MS/s (mặc định 10 MS/s) `[DS]`.
- Output USB3 + LAN `[ẢNH]`.
- Line: 2048 điểm, Δf ≈ 24,4 kHz `[ĐO]`/`[TÍNH]`.

## Ràng buộc
- Chưa nghiệm thu đường HI/L-band cho tới khi truy được feed → LNB → Receiver và đo đáp tuyến.
- Trước khi tin phát hiện: đo T_sys, SEFD, beam, RFI thật (cổng G0 trong [[Trạng thái hiện tại]]).

Liên quan: [[Pipeline phát hiện pulsar]], [[Pulsar có thể đo gì]].
