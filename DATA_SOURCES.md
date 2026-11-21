# Nguồn dữ liệu dùng để kiểm chứng (KHÔNG kèm trong repo)

Repo này chỉ chứa **mã nguồn + tài liệu của ứng dụng**. Dữ liệu quan sát (hàng trăm MB)
không được đưa lên git; tải lại theo bảng dưới rồi đặt vào `data/`.

Tất cả dữ liệu dưới đây là của bên thứ ba, dùng cho **kiểm chứng phi thương mại**,
kèm ghi công theo giấy phép gốc.

| Thư mục | Nội dung | Nguồn | Giấy phép |
|---|---|---|---|
| `data/B0329+54.fil` | 3 xung B0329+54, Greenburst/GBT, 33.5 MB | Zenodo [5570222](https://zenodo.org/records/5570222) — Joseph W. Kania | CC-BY-4.0 |
| `data/stress/B0531+21.fil` | Cutout Cua, 336 MHz, RFI dày (bộ dữ liệu paper **IQRM**) | Zenodo [5875992](https://zenodo.org/records/5875992) — Joseph Kania | CC-BY-4.0 |
| `data/stress/B1828.fil` | 4096 kênh, RFI xung | Zenodo [5875992](https://zenodo.org/records/5875992) | CC-BY-4.0 |
| `data/stress/empty_example.fil` | Đối chứng âm: **chỉ RFI** | Zenodo [5875992](https://zenodo.org/records/5875992) | CC-BY-4.0 |
| `data/iq/crab-giantpulse.sigmf-*` | **IQ thô** 20 MS/s, 410 MHz, giant pulse Cua, kính Dwingeloo 25 m | Zenodo [13143544](https://zenodo.org/records/13143544) — M. Fine, T. J. Dijkema, J. Hessels | CC-BY-4.0 |
| `data/stress/28.fil`, `small.fil`, `empty.fits`, `test_4pol.fits` | File test định dạng (kể cả file hỏng) | [thepetabyteproject/your](https://github.com/thepetabyteproject/your) `tests/data/` | MIT |
| `data/stress/tutorial.fil` | Ví dụ chính thức, mẫu **2-bit** | [ewanbarr/sigpyproc](https://github.com/ewanbarr/sigpyproc) `examples/` | MIT |
| `data/extra/B1822-09_650MHz.fits` | **PSRFITS thật** (GMRT, 650 MHz, 4096 kênh nhưng chỉ **1 tích phân**) — dùng để thử đọc header thật (`NSBLK='*'`, `NCHAN`≠`OBSNCHAN`, TDIM) | Zenodo [18497372](https://zenodo.org/records/18497372) (SUSPECT) | xem trang Zenodo |
| `data/extra/ar/*.ar` | **3 file MeerKAT/TRAPUM** (LMC) — thực chất là **PSRFITS** đổi đuôi, `TBIN = 0` (dữ liệu fold/single-pulse) → kiểm tra nhận dạng theo **nội dung** và thông báo lỗi rõ ràng | Zenodo [12723577](https://zenodo.org/records/12723577) | xem trang Zenodo |
| `data/extra/B0329+54_{4bit,16bit,float32,long21s}.fil` | **Sinh từ** `data/B0329+54.fil` bởi `code/make_test_data.py` (4-bit, 16-bit, float32, bản 21 s có gap) + `manifest.json` | — | như nguồn gốc (CC-BY-4.0) |
| `data/stress/injected_*` | **Tự sinh** bởi `stress_test.py` (tiêm pulsar vào nền RFI thật) | — | — |

## Tải nhanh

```bash
# Dữ liệu thật (Linux/macOS: dùng curl; Windows: PowerShell dùng Invoke-WebRequest)
curl -L -o data/B0329+54.fil        https://zenodo.org/api/records/5570222/files/B0329+54.fil/content
curl -L -o data/iq/crab-giantpulse.sigmf-data  https://zenodo.org/api/records/13143544/files/crab-giantpulse.sigmf-data/content
curl -L -o data/iq/crab-giantpulse.sigmf-meta  https://zenodo.org/api/records/13143544/files/crab-giantpulse.sigmf-meta/content
curl -L -o data/stress/empty_example.fil       https://zenodo.org/api/records/5875992/files/empty_example.fil/content
```

Toàn bộ URL còn lại: `docs/06_phan_cung_toi_gian_va_ghi_tu_dong.md` §9–§10.

## Giấy phép mã nguồn

Mã nguồn và tài liệu trong repo này: xem `LICENSE` (MIT).
Dữ liệu bên thứ ba giữ nguyên giấy phép gốc như bảng trên.
