# Pulsar có thể đo gì

Nguồn đầy đủ: `docs/03_do_duoc_gi_tu_pulsar.md`. Số liệu suy ra bằng `python code/psr_targets.py --derived`.

## Làm được ngay với RTP-3.7 (khi SNR đủ)
| Đại lượng | Điều kiện | Ghi chú |
|---|---|---|
| **P** (chu kỳ) | fold + timing | ngay |
| **W50**, dạng hồ sơ | hồ sơ SNR ≥ 10–15 | hình học vùng phát xạ |
| **DM** | quét DM (A11b) | đại lượng đo được; khoảng cách suy ra từ đó |
| **Đuôi tán xạ τ_sc** | SNR cao | môi trường liên sao |
| **Chỉ số phổ α, S** | 2 tần số (408 + 1400 MHz) | cần front-end 408 MHz |

## Vị trí: chảo 3.7 m không phải dụng cụ đo vị trí
| Việc | Độ chính xác | Điều kiện |
|---|---|---|
| Xác nhận đang trỏ đúng mục tiêu | ±2° (nửa beam) | beam ≈ 4° + encoder |
| Đo độ lệch trỏ (pointing model) | ±0,2–0,5° | map 5 điểm trên Cas A / Mặt Trăng |
| Vị trí pulsar bằng map chùm tia | ±0,5° | SNR ≥ 20, quét 5 điểm |
| Vị trí từ timing (TOA astrometry) | 0,1–1″ | 6–12 tháng TOA + GPSDO + barycentric |

Vị trí lấy từ ATNF; việc của ta là kiểm tra và hiệu chỉnh mô hình trỏ.

## Cần giai đoạn 4 (timing dài hạn) và GPSDO
- **Ṗ** → từ trường `B`, tuổi, `Ė`. Không đo trực tiếp từ P mà từ fit TOA dài hạn. Nút thắt là đồng hồ (GPSDO), hiệu chỉnh barycentric và template ổn định, không phải độ nhạy.
- **Glitch, thị sai, quỹ đạo sao đôi**: cần timing nhiều năm.

## Không làm được với cấu hình hiện tại
- Scintillation (cần chuỗi động phổ dài và SNR cao).
- Giant pulse, nulling, mode change: rất khó với xung đơn trên kính này.
- RM và hình học từ trường (RVM): cần 2 phân cực, thiết bị chưa có.
- Hấp thụ HI về phía pulsar yếu: cần continuum mạnh.

## Lưu ý về khoảng cách
`d = DM / ⟨n_e⟩` chỉ đúng bậc độ lớn. Quy tắc: báo DM (đo được), chỉ báo khoảng cách kèm sai số ±50 % hoặc kèm mô hình (NE2001/YMW16). Ví dụ Vela: `d_DM ≈ 2.3 kpc` nhưng khoảng cách VLBI ≈ 0.29 kpc, sai ~8 lần.

Liên quan: [[B0329+54 — mẫu kiểm chứng]].
