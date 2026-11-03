# BÁO CÁO TIẾN ĐỘ XÂY DỰNG HỆ THỐNG NUTEE

*Nền tảng mô phỏng thương mại điện tử và xử lý dữ liệu phục vụ bài toán gợi ý sản phẩm*

**Ngày báo cáo:** 31/10/2026  
**Sinh viên thực hiện:** ........................................  
**MSSV:** ........................................

## 1. Mục tiêu và phạm vi công việc

Thưa cô, trong giai đoạn vừa qua, em tập trung xây dựng phần ứng dụng và hệ thống dữ liệu cho bài toán gợi ý sản phẩm. Mục tiêu là tạo một môi trường mua sắm giả lập, trong đó các hành vi của người dùng được ghi nhận, lưu trữ và xử lý thành dữ liệu có thể sử dụng cho việc phát triển mô hình gợi ý.

Hệ thống được đặt tên là **NUTEE**. Người dùng có thể xem sản phẩm, tìm kiếm, thêm vào danh sách yêu thích, thêm vào giỏ hàng và thực hiện đặt hàng thử. Từ các thao tác này, hệ thống tạo ra lịch sử tương tác giữa người dùng và sản phẩm.

Ở phiên bản hiện tại, phần đã thực hiện gồm website, backend, cơ sở dữ liệu sản phẩm, tracking hành vi, bộ sinh dữ liệu giả lập và pipeline xử lý dữ liệu. **Module AI gợi ý sản phẩm chưa được triển khai trong bản hiện tại**; phần dữ liệu đã được chuẩn bị để bàn giao và tích hợp module này ở giai đoạn tiếp theo.

## 2. Xây dựng website và các chức năng mua sắm

Em đã xây dựng giao diện bằng React/Vite và backend bằng FastAPI. Website hiện có các chức năng chính:

- Xem danh sách sản phẩm và thông tin chi tiết.
- Tìm kiếm và lọc sản phẩm theo danh mục.
- Xem thông số kỹ thuật, giá và tình trạng tồn kho.
- Thêm sản phẩm vào danh sách yêu thích.
- Thêm, xóa sản phẩm trong giỏ hàng.
- Thực hiện checkout giả lập.
- Chọn người dùng demo để quan sát lịch sử tương tác của từng người.

Website đóng vai trò là nơi phát sinh dữ liệu hành vi. Ví dụ, khi một người dùng xem danh sách, nhấp vào một sản phẩm rồi thêm vào giỏ hàng, hệ thống ghi nhận các thao tác này thành những sự kiện riêng biệt. Nhờ đó, dữ liệu thu được thể hiện được các bước trong quá trình mua sắm.

Với checkout, backend đã có cơ chế tạo đơn hàng thử, cập nhật tồn kho và ghi nhận sự kiện mua hàng trong cùng một giao dịch cơ sở dữ liệu. Hệ thống cũng xử lý yêu cầu checkout lặp lại nhằm tránh tạo trùng đơn hàng.

Các chức năng này phục vụ mục đích demo. Việc chọn người dùng chưa phải cơ chế đăng nhập thực tế và checkout chưa tích hợp thanh toán thật.

## 3. Thiết kế dữ liệu sản phẩm

Em đã tổ chức dữ liệu sản phẩm theo cấu trúc quan hệ, gồm bảy bảng chính:

| Bảng | Nội dung quản lý |
| --- | --- |
| `product` | Thông tin chung của sản phẩm |
| `product_variant` | Biến thể bán hàng, SKU, giá và tồn kho |
| `product_specification` | Thông số kỹ thuật |
| `brand` | Thương hiệu |
| `product_brand` | Liên kết sản phẩm với thương hiệu |
| `category` | Danh mục sản phẩm |
| `product_category` | Liên kết sản phẩm với danh mục |

Việc tách dữ liệu như trên giúp quản lý sản phẩm rõ ràng và hạn chế lặp thông tin. Chẳng hạn, thông số của một laptop có thể gồm CPU, RAM, SSD và màn hình; trong khi tai nghe có các thông số khác như Bluetooth, driver và chống ồn.

Những thông tin này cũng là đầu vào có thể sử dụng cho phương pháp gợi ý dựa trên nội dung sản phẩm sau này.

Hệ thống phân biệt ID dùng trong cơ sở dữ liệu với mã sản phẩm dùng trong website và sự kiện. Ví dụ, mã `P0001` được dùng để liên kết sản phẩm với lịch sử tương tác. Việc thống nhất cách sử dụng mã giúp tránh sai lệch khi nối dữ liệu giữa các thành phần.

Hiện ứng dụng sử dụng **SQLite**. Em đã có bản mô tả cấu trúc SQL dành cho PostgreSQL để phục vụ việc bàn giao hoặc chuyển đổi sau này, nhưng PostgreSQL chưa phải cơ sở dữ liệu đang vận hành của phiên bản hiện tại.

## 4. Thu thập và kiểm soát dữ liệu hành vi

Em đã xây dựng cơ chế tracking cho tám loại hành vi:

| Sự kiện | Ý nghĩa |
| --- | --- |
| `product_impression` | Sản phẩm xuất hiện trong vùng nhìn thấy của người dùng |
| `product_click` | Người dùng nhấp vào sản phẩm |
| `product_view` | Người dùng xem chi tiết sản phẩm |
| `search` | Người dùng tìm kiếm |
| `add_to_wishlist` | Thêm vào danh sách yêu thích |
| `add_to_cart` | Thêm vào giỏ hàng |
| `remove_from_cart` | Xóa khỏi giỏ hàng |
| `purchase` | Mua hàng qua checkout giả lập |

Mỗi sự kiện có mã định danh, thời gian phát sinh, người dùng, phiên truy cập và mã sản phẩm nếu hành vi liên quan đến một sản phẩm cụ thể. Một số sự kiện còn lưu ngữ cảnh như trang hiển thị, danh sách sản phẩm và vị trí của sản phẩm trong danh sách.

Để tăng độ tin cậy của dữ liệu, em đã bổ sung các bước kiểm tra:

- Kiểm tra những trường bắt buộc theo từng loại sự kiện.
- Chuẩn hóa thời gian về UTC.
- Sử dụng mã sự kiện để chống lưu trùng.
- Quản lý phiên truy cập; frontend đổi phiên khi đổi người dùng hoặc không hoạt động quá 30 phút.
- Chỉ ghi nhận impression khi thẻ sản phẩm xuất hiện ít nhất 50% trong vùng nhìn thấy.

Riêng sự kiện mua hàng được tạo từ phía backend thông qua checkout. Cách này giúp sự kiện mua hàng gắn với xử lý đơn hàng, thay vì chỉ dựa vào một thông báo gửi lên từ trình duyệt.

Hệ thống cũng đã có phần tích hợp PostHog và chương trình xuất dữ liệu từ PostHog về pipeline. Đây là nhánh tùy chọn; bản demo vẫn hoạt động bằng dữ liệu lưu tại ứng dụng khi không cấu hình PostHog. Việc lưu sự kiện thành công tại ứng dụng và việc PostHog tiếp nhận sự kiện được xem là hai bước riêng biệt.

## 5. Xây dựng bộ sinh dữ liệu giả lập

Do chưa có lượng người dùng thực tế để tạo lịch sử tương tác đủ lớn, em đã xây dựng bộ sinh dữ liệu giả lập.

Bộ sinh mô phỏng hành vi theo phiên mua sắm, với các bước như nhìn thấy sản phẩm, nhấp vào, xem chi tiết, thêm vào danh sách yêu thích, thêm vào giỏ và mua hàng. Quá trình mô phỏng có yếu tố ngẫu nhiên, ảnh hưởng của vị trí hiển thị và ngân sách của phiên để tạo sự khác biệt giữa các lượt tương tác.

Bộ sinh có ba nhóm kịch bản:

- **Sở thích ổn định:** người dùng duy trì nhóm sản phẩm quan tâm.
- **Sở thích thay đổi:** nhóm sản phẩm quan tâm thay đổi về cuối khoảng thời gian mô phỏng.
- **Người dùng hoặc sản phẩm mới:** tạo tình huống ít lịch sử tương tác, phục vụ nghiên cứu bài toán cold-start.

Bộ sinh sử dụng seed và cấu hình để có thể tái tạo dữ liệu khi các đầu vào giữ nguyên. Dữ liệu xuất ra có manifest và mã hash để hỗ trợ đối chiếu giữa các lần chạy.

Theo log của bộ dữ liệu demo đã lưu, với seed 42, quy mô dữ liệu như sau:

| Thành phần | Số lượng |
| --- | ---: |
| Người dùng giả lập | 1.000 |
| Sản phẩm | 300 |
| SKU | 300 |
| Thông số kỹ thuật | 1.860 |
| Thương hiệu | 20 |
| Danh mục | 10 |
| Sự kiện hành vi | 100.000 |
| Phiên tương tác | 7.348 |

Phân bố sự kiện trong bộ dữ liệu này:

| Loại sự kiện | Số lượng |
| --- | ---: |
| Hiển thị sản phẩm | 58.778 |
| Nhấp vào sản phẩm | 16.393 |
| Xem chi tiết | 16.393 |
| Thêm vào giỏ hàng | 4.788 |
| Thêm vào danh sách yêu thích | 2.426 |
| Mua hàng giả lập | 1.222 |
| **Tổng** | **100.000** |

Website hỗ trợ tracking tìm kiếm và xóa khỏi giỏ hàng, nhưng bộ dữ liệu mô phỏng trên chưa sinh hai loại hành vi này.

Các sự kiện mua hàng do bộ sinh tạo ra chỉ biểu diễn lịch sử hành vi, không tạo đơn hàng thực và không làm giảm tồn kho. Đồng thời, toàn bộ dữ liệu này là dữ liệu giả lập, chưa thể dùng để khẳng định hành vi hoặc hiệu quả kinh doanh của người dùng thực tế.

## 6. Xây dựng pipeline xử lý dữ liệu

Em đã triển khai pipeline theo ba lớp Bronze, Silver và Gold. Mỗi lớp có một nhiệm vụ riêng để dễ kiểm tra dữ liệu từ lúc thu thập đến lúc bàn giao.

Luồng xử lý chính:

```text
Website / Bộ sinh dữ liệu
           ↓
    Lưu sự kiện tại ứng dụng
           ↓
    Bronze: dữ liệu thô
           ↓
    Silver: dữ liệu đã làm sạch
           ↓
    Gold: dữ liệu tổng hợp
           ↓
    Đầu vào cho module gợi ý sản phẩm
```

### 6.1. Lớp Bronze — lưu dữ liệu thô

Bronze giữ các sự kiện đầu vào để có thể kiểm tra lại hoặc chạy lại quá trình xử lý. Với nguồn dữ liệu tại ứng dụng, pipeline kiểm tra mã sự kiện đã có trong Bronze trước khi bổ sung dữ liệu, nhằm hạn chế ghi trùng khi chạy lại.

### 6.2. Lớp Silver — chuẩn hóa và làm sạch

Silver thực hiện kiểm tra cấu trúc sự kiện, chuẩn hóa thời gian, kiểm tra liên kết với người dùng và sản phẩm, loại bỏ dữ liệu trùng và xử lý phiên truy cập.

Những sự kiện không đạt yêu cầu được ghi ra dữ liệu riêng kèm lý do loại bỏ. Cách này giúp em có thể tìm nguyên nhân khi dữ liệu đầu vào có vấn đề, thay vì chỉ thấy số lượng đầu ra bị giảm.

Trong lần chạy demo đã ghi nhận, pipeline xử lý 100.000 sự kiện và không có sự kiện bị loại. Kết quả này phản ánh bộ dữ liệu thử nghiệm đó, chưa có nghĩa pipeline sẽ không gặp dữ liệu lỗi ở các nguồn khác.

### 6.3. Lớp Gold — tổng hợp dữ liệu phục vụ sử dụng

Gold hiện tạo hai bảng:

| Bảng | Nội dung | Số dòng trong lần chạy đã ghi nhận |
| --- | --- | ---: |
| `user_item_event_counts` | Đếm từng loại tương tác của mỗi người dùng với mỗi sản phẩm; lưu thời điểm đầu và cuối | 90.559 |
| `session_sequences` | Lưu chuỗi sản phẩm, loại sự kiện và thời gian theo từng phiên | 7.348 |

Ví dụ, bảng đếm tương tác có thể cho biết một người dùng đã xem một sản phẩm bao nhiêu lần và thêm vào giỏ bao nhiêu lần. Bảng chuỗi phiên cho biết thứ tự các thao tác, giúp nghiên cứu diễn biến hành vi trong một lần truy cập.

Phần Gold hiện giữ các thông tin tổng hợp trung tính. Việc chọn trọng số cho click, giỏ hàng hoặc mua hàng, tính mức độ quan tâm hay xây dựng đặc trưng cho mô hình sẽ thuộc bước phát triển recommendation.

Ngoài ra, pipeline có mã lần chạy và manifest để xác định bộ kết quả hiện hành. Các bảng Gold được ghi hoàn tất trước khi cập nhật manifest, giúp thành phần đọc dữ liệu nhận được một bộ kết quả đồng nhất.

## 7. Theo dõi hệ thống và khả năng kiểm tra

Em đã bổ sung trang Data trace và các API nội bộ để quan sát sự kiện, số lượng dữ liệu và trạng thái pipeline. Hệ thống cũng ghi audit log cho các bước xử lý chính.

Những thành phần này hỗ trợ việc kiểm tra một thao tác đã được ghi nhận hay chưa, dữ liệu đang ở bước nào và pipeline có loại bỏ sự kiện nào không.

Về đóng gói, ứng dụng đã có Docker Compose cho backend, frontend, tác vụ tạo dữ liệu demo và môi trường chạy kiểm thử. Dữ liệu ứng dụng được lưu trong volume để có thể giữ lại khi tạo lại container.

Theo biên bản xác minh ngày **27/10/2026**, kết quả đã ghi nhận gồm:

- **30 kiểm thử thành công**, bao phủ các phần sản phẩm, checkout, tracking, chất lượng dữ liệu, pipeline và xử lý liên quan đến PostHog.
- Build backend và frontend thành công.
- Backend đạt trạng thái healthy; các đường dẫn API và trang frontend được kiểm tra trả phản hồi thành công.
- Kiểm tra khóa ngoại trong SQLite không phát hiện lỗi.
- Pipeline tạo được các bảng Gold từ bộ 100.000 sự kiện.

Các kết quả trên là bằng chứng kiểm tra chức năng đã lưu. Phần kiểm tra frontend mới gồm build và kiểm tra phản hồi HTTP, chưa phải kiểm thử đầy đủ mọi tương tác trên trình duyệt.

## 8. Phần chuẩn bị cho hệ gợi ý sản phẩm

Đối với bài toán recommendation, kết quả hiện tại của em là chuẩn bị được các nhóm đầu vào:

- Catalog sản phẩm có danh mục, thương hiệu và thông số kỹ thuật.
- Lịch sử tương tác đã làm sạch.
- Số lần tương tác giữa người dùng và sản phẩm theo từng loại hành vi.
- Chuỗi tương tác theo phiên.

Các dữ liệu này có thể được sử dụng để thử nghiệm phương pháp dựa trên nội dung sản phẩm, dựa trên tương tác người dùng hoặc kết hợp nhiều phương pháp.

Tuy nhiên, thư mục recommendation trong phiên bản hiện tại mới là khung bàn giao. Chưa có mô hình được huấn luyện, API phục vụ kết quả gợi ý hay kết quả đánh giá chất lượng mô hình. Trang chủ hiện hiển thị danh sách sản phẩm thông thường.

Khi triển khai phần AI, dữ liệu cần được chia theo thời gian và các bảng tổng hợp phải được tính lại theo mốc chia phù hợp, để tránh sử dụng thông tin tương lai khi huấn luyện hoặc đánh giá.

## 9. Benchmark hệ thống dữ liệu đã bổ sung

Em đã bổ sung chương trình benchmark cho pipeline Python/pandas/SQLite và chạy đo trên máy Windows ngày 31/10/2026. Phép đo sử dụng dữ liệu synthetic riêng, không thay đổi database demo và không gửi dữ liệu đến PostHog.

### 9.1. Thiết lập phép đo

- Hai mức dữ liệu: **10.000 và 100.000 sự kiện**, seed 42, mỗi mức lặp **3 lần**.
- Mỗi lần lặp đo hai chế độ: `first_load` khi Bronze/Silver/Gold chưa có, và `rerun` trên cùng dataset đã xử lý.
- Mỗi lượt ETL chạy trong process mới; SQLite đầu vào được sao chép từ dataset seed bằng backup API.
- Môi trường: Windows 11, Python 3.13.2, 16 logical CPUs; OPENBLAS_NUM_THREADS=1, OMP_NUM_THREADS=2.
- Giữ cùng cutoff dữ liệu 16/02/2026 UTC, sau khoảng thời gian do simulator tạo.
- Không xóa disk cache của hệ điều hành; `first_load` không đồng nghĩa với cold-cache.

Thời gian đo gồm khởi tạo, xử lý Bronze, Silver và Gold. Thời gian sinh dữ liệu, import module và kiểm tra đầu ra không nằm trong tổng thời gian ETL. Đỉnh RAM là peak working set/RSS của process đến ngay sau ETL, bao gồm phần import, không phải RAM tăng thêm của riêng pipeline.

### 9.2. Kết quả đo

Bảng dưới dùng **median của 3 lần lặp**. File JSON giữ từng lượt cùng min/max để đối chiếu.

| Sự kiện | Chế độ | Tổng (giây) | Bronze (giây) | Silver (giây) | Gold (giây) | Sự kiện/giây | Peak RAM (MiB) |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 10,000 | first_load | 1.886 | 0.223 | 0.923 | 0.701 | 5,302.287 | 151.305 |
| 10,000 | rerun | 1.933 | 0.331 | 0.898 | 0.699 | 5,172.169 | 144.918 |
| 100,000 | first_load | 28.482 | 1.655 | 15.292 | 11.502 | 3,510.978 | 486.816 |
| 100,000 | rerun | 30.717 | 3.221 | 15.778 | 11.770 | 3,255.499 | 491.930 |

Các median từng bước được tính riêng nên tổng các median thành phần có thể khác nhẹ median tổng thời gian.

### 9.3. Kiểm tra chất lượng và tính nhất quán

Cả 12 lượt đo đều đạt các kiểm tra dữ liệu. Với từng mức dữ liệu, số sự kiện hợp lệ bằng số sự kiện yêu cầu; không có sự kiện bị loại hoặc bị loại do trùng trong bộ dữ liệu sạch này. Khi chạy lại, nội dung Silver (sau khi bỏ trường thời điểm ingest) và hai bảng Gold giữ nguyên; số file và dung lượng Bronze không tăng.

Em kiểm tra thêm tổng số tương tác ở bảng đếm và tổng chiều dài chuỗi phiên để đối chiếu với dữ liệu Silver. Bộ kiểm thử gồm **32 test đã đạt**, trong đó có kiểm tra mới cho số liệu benchmark khi gặp sự kiện lỗi, trùng và dataset rỗng. Khi chạy trong sandbox Windows, em dùng thư mục tạm riêng với quyền kế thừa để tránh lỗi tạo thư mục tạm của pytest. Một cảnh báo deprecation từ Starlette/httpx vẫn còn; không có test chức năng thất bại trong lần chạy hoàn tất.

Dung lượng đầu ra của lần lặp đầu, chế độ first_load:

| Sự kiện | Bronze (MiB) | Silver (MiB) | Gold hiện hành (MiB) |
| ---: | ---: | ---: | ---: |
| 10,000 | 0.740 | 0.655 | 0.300 |
| 100,000 | 7.216 | 5.950 | 2.537 |

Gold vẫn tạo generation mới theo thiết kế, nên tổng dung lượng các generation có thể tăng khi chạy lại. Tính nhất quán ở đây là nội dung dữ liệu không đổi, không có nghĩa mọi file trên ổ đĩa giữ nguyên.

### 9.4. Nhận xét và phần cần đo tiếp

Trong các lượt đo hiện tại, Silver và Gold chiếm phần lớn thời gian. Điều này giúp xác định nơi cần khảo sát tối ưu tiếp: làm sạch dữ liệu và tổng hợp chuỗi phiên. Chạy lại vẫn đọc, làm sạch và tổng hợp toàn bộ dữ liệu; cơ chế chống trùng Bronze chưa biến pipeline thành xử lý gia tăng cho toàn bộ các lớp.

Kết quả trên chỉ phản ánh benchmark batch cục bộ trên dữ liệu synthetic và cấu hình máy đã ghi nhận. Em chưa dùng các con số này để kết luận năng lực production hoặc hiệu quả recommendation. Các phần dự kiến bổ sung tiếp gồm độ trễ từ sự kiện đến Gold, tải API đồng thời, ingestion PostHog và thử nghiệm dữ liệu lớn hơn. Với ba lần lặp, báo cáo sử dụng median/min/max, chưa suy diễn p95 hoặc p99.

Bằng chứng chi tiết:

- [Báo cáo benchmark](../runtime/benchmarks/20261031T094827Z-db9218ff/report.md).
- [Kết quả JSON và metadata tái lập](../runtime/benchmarks/20261031T094827Z-db9218ff/results.json).

---

## Tài liệu đối chiếu

Các đường dẫn dưới đây tính từ thư mục gốc dự án NUTEE (`mock_reccom_system`):

- `README.md`: phạm vi, kiến trúc và hướng dẫn sử dụng hệ thống.
- `docs/demo-log.json`: quy mô dữ liệu, phân bố sự kiện và đầu ra Gold.
- `VERIFICATION.md`: biên bản xác minh ngày 27/10/2026.
- `pipeline/run_pipeline.py`: luồng xử lý và cách tạo các bảng Gold.
- `recommendation/README.md`: phạm vi bàn giao cho phần recommendation.

*Các mục 1–8 dựa trên mã nguồn, log demo và biên bản xác minh đã lưu. Mục 9 là kết quả benchmark mới ngày 31/10/2026; chi tiết từng lượt, cấu hình và hash mã nguồn được lưu trong results.json.*
