# Benchmark pipeline dữ liệu NUTEE

Benchmark đo pipeline Python/pandas/SQLite hiện tại, dùng dữ liệu synthetic riêng.
Không sửa dữ liệu ứng dụng, không gọi PostHog và không huấn luyện mô hình.

## Chạy local

Từ thư mục gốc dự án, dùng môi trường Python đã cài `backend/requirements.txt`:

```powershell
.\.venv\Scripts\python.exe -m scripts.benchmark --sizes 10000 100000 --repeats 3 --seed 42
```

Kiểm tra nhanh với dữ liệu nhỏ:

```powershell
.\.venv\Scripts\python.exe -m scripts.benchmark --sizes 100 --repeats 2
```

Mỗi lệnh tạo thư mục riêng dưới `runtime/benchmarks/<UTC timestamp>-<id>/`:

- `results.json`: metadata môi trường, hash mã nguồn/config, dataset và từng lượt đo.
- `report.md`: bảng kết quả có thể đưa vào báo cáo tiến độ.
- `run-*.json` và `run-*.log`: kết quả/log của mỗi process ETL.
- `generated-*.json`: seed, hash, cấu hình và thời gian sinh dữ liệu.
- `seed-*`, `data-*`: SQLite và dữ liệu các lớp của riêng benchmark.

Thư mục runtime không được commit. Giữ `results.json` và `report.md` nếu muốn lưu
bằng chứng; dataset benchmark có thể lớn. Script không tự xóa dữ liệu cũ.

## Chạy bằng Docker

Sau khi build backend có mã benchmark:

```sh
docker compose build backend
docker compose run --rm --no-deps -v "./runtime/benchmarks:/benchmarks" backend python -m scripts.benchmark --output-root /benchmarks --sizes 10000 100000 --repeats 3
```

Benchmark tự đặt `NUTEE_DATA_DIR` của worker thành dataset riêng dưới output root;
không dùng `/app/data` của ứng dụng. Không so sánh trực tiếp kết quả Docker và local
mà bỏ qua giới hạn CPU/RAM hoặc loại filesystem.

## Phương pháp

1. Sinh một dataset cho mỗi kích thước, seed 42 mặc định, không gửi sự kiện ra ngoài.
2. Mỗi lần lặp dùng SQLite backup API để sao chép dataset seed sang thư mục mới.
3. `first_load` chạy ETL khi chưa có Bronze/Silver/Gold.
4. `rerun` chạy lại trên cùng dataset, kiểm tra nội dung đầu ra không đổi.
5. Mỗi lượt ETL chạy trong process mới; cùng seed, config, cutoff và dữ liệu đầu vào.
6. Báo median/min/max từ các lần lặp; không báo p95/p99 với chỉ ba mẫu.

Không chủ động xóa disk cache của hệ điều hành. Vì vậy `first_load` chỉ có nghĩa
là các lớp dữ liệu chưa tồn tại, không phải phép đo cold-cache. Thời gian sinh
dữ liệu được lưu riêng và không tính vào tốc độ pipeline.

## Định nghĩa chỉ số

| Chỉ số | Phạm vi |
| --- | --- |
| `initialize` | Khởi tạo DB, run ID và audit ban đầu |
| `bronze` | Đọc Bronze cũ để chống trùng, đọc SQLite/catalog, append và đọc lại Bronze |
| `silver` | Làm sạch, ghi Silver/rejected Parquet và audit |
| `gold` | Tổng hợp, ghi cả hai bảng Gold, publish manifest và audit |
| `total` | Tổng bốn bước; không tính import, sinh dữ liệu hay kiểm tra đầu ra |
| Events/s | Số dòng đầu vào Bronze chia tổng thời gian ETL |
| CPU seconds | CPU user + kernel của process trong lúc gọi ETL |
| CPU % | CPU seconds / wall seconds × 100; một core bằng 100%, có thể vượt 100% |
| Peak RSS | Đỉnh working set/RSS của process đến ngay sau ETL, gồm imports; không gồm worker sinh dữ liệu |
| Storage bytes | Dung lượng logic file, không phải allocated disk space; tách Gold hiện hành và toàn bộ generation |
| Quality | Số đầu vào, hợp lệ, bị loại, trùng và nguyên nhân bị loại |

RAM trên Windows lấy `PeakWorkingSetSize`; Linux/macOS dùng `ru_maxrss` và quy đổi
về bytes. Đây là đỉnh của process đến sau ETL, không phải mức RAM tăng thêm của
riêng hàm ETL. Không lấy RAM lúc kiểm tra bảng đầu ra vào số đo này.

## Kiểm tra tính đúng đắn

- Đầu vào = hợp lệ + bị loại + bị loại do trùng.
- Với dataset sạch do simulator tạo, số hợp lệ phải bằng kích thước yêu cầu.
- Tổng event_count ở Gold bằng số Silver events có product_id.
- Tổng chiều dài chuỗi phiên bằng số Silver events.
- Hash nội dung Silver (bỏ ingested_at) và cả hai bảng Gold phải giống giữa các lượt.
- Chạy lại không tăng số file hoặc dung lượng Bronze.

Các generation Gold vẫn được tạo mới theo thiết kế; không tuyên bố dung lượng
toàn dataset bất biến khi chạy lại. Khi một kiểm tra thất bại, benchmark trả mã lỗi.

## Phạm vi chưa đo

Đây là benchmark batch cục bộ trên dữ liệu synthetic sạch. Chưa đo tải đồng thời
của API, tốc độ ingestion PostHog, độ trễ event-to-Gold, hệ phân tán hoặc chất lượng
recommendation. Các unit test có kiểm tra dữ liệu lỗi/trùng; số liệu hiệu năng trên
dataset sạch không đại diện cho tải lỗi lớn. Cutoff được lấy sau cuối timeline
simulator để các lần chạy dùng cùng mốc, không phụ thuộc ngày chạy.

Kiểm thử:

```powershell
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
```
