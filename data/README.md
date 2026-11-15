# Dữ liệu

**Nguồn:** Brazilian E-Commerce Public Dataset by Olist — https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce

## Cách lấy dữ liệu

**Cách 1 – trình duyệt:** đăng nhập Kaggle, tải file zip ở link trên, giải nén 9 file CSV vào `data/raw/`.

**Cách 2 – dòng lệnh** (chạy ở thư mục gốc repo):

```bash
curl -fL --retry 3 -o data/raw/olist.zip https://www.kaggle.com/api/v1/datasets/download/olistbr/brazilian-ecommerce
unzip -o data/raw/olist.zip -d data/raw
```

Trên Windows không có `unzip` thì dùng PowerShell:

```powershell
Expand-Archive data/raw/olist.zip -DestinationPath data/raw -Force
```

File zip khoảng 45 MB, giải nén ra khoảng 126 MB.

`data/raw/` không được commit (xem `.gitignore`).

## Các file

| File | Số dòng | Nội dung |
|---|---|---|
| olist_orders_dataset.csv | 99.441 | Đơn hàng, trạng thái, 5 mốc thời gian |
| olist_order_items_dataset.csv | 112.650 | Từng đơn vị hàng trong đơn (không có cột số lượng) |
| olist_order_payments_dataset.csv | 103.886 | Thanh toán theo đơn |
| olist_order_reviews_dataset.csv | 99.224 | Đánh giá 1–5 sao, bình luận |
| olist_customers_dataset.csv | 99.441 | Khách theo đơn (`customer_unique_id` là mã khách thật) |
| olist_sellers_dataset.csv | 3.095 | Người bán |
| olist_products_dataset.csv | 32.951 | Sản phẩm, danh mục, kích thước |
| olist_geolocation_dataset.csv | 1.000.163 | Mã bưu điện → tọa độ (trùng nhiều) |
| product_category_name_translation.csv | 71 | Dịch tên danh mục |

## Dữ liệu mẫu (`data/sample/`)

> ⚠️ **Chỉ dùng để chạy thử pipeline và chạy test.** Mọi số liệu trong báo cáo, dashboard và mô hình
> phải tính trên bộ đầy đủ trong `data/raw/`.

Đây là **tập con cắt từ chính bộ gốc**: mỗi dòng được chép nguyên văn, không sinh thêm, không sửa giá trị.
Tên 9 file giống hệt `data/raw/`, nên chỉ cần đổi `RAW_DATA_DIR=data/sample` trong `.env` là ETL chạy trên bộ mẫu.

| File | Số dòng |
|---|---|
| olist_orders_dataset.csv | 1.479 |
| olist_order_items_dataset.csv | 1.631 |
| olist_order_payments_dataset.csv | 1.542 |
| olist_order_reviews_dataset.csv | 1.479 |
| olist_customers_dataset.csv | 1.479 |
| olist_products_dataset.csv | 1.337 |
| olist_sellers_dataset.csv | 615 |
| olist_geolocation_dataset.csv | 8.942 |
| product_category_name_translation.csv | 71 (chép nguyên file) |

Tổng khoảng 1,6 MB.

**Cách lấy mẫu** (script [`src/etl/make_sample.py`](../src/etl/make_sample.py), seed cố định = 42):

1. 70 đơn đã giao ngẫu nhiên cho mỗi tháng từ 01/2017 đến 08/2018.
2. Thêm tối đa 8 đơn cho mỗi nhóm "ca đặc biệt" để ETL có dữ liệu bẩn mà xử lý:
   - mỗi trạng thái khác `delivered` (canceled, unavailable, shipped, invoiced, processing, created, approved);
   - đơn không có dòng sản phẩm;
   - đơn có thời điểm giao cho vận chuyển trước thời điểm duyệt;
   - đơn có sản phẩm thuộc danh mục chưa có bản dịch;
   - đơn thuộc giai đoạn thưa (2016, 09–10/2018).
3. Kéo theo toàn bộ dòng liên quan ở các file khác (khách, sản phẩm, người bán, thanh toán, review).
4. Geolocation: tối đa 5 dòng cho mỗi mã bưu điện được dùng, cộng 42 điểm nằm ngoài lãnh thổ Brazil.

Đã kiểm tra: không có bản ghi mồ côi giữa các bảng (đơn → khách, dòng sản phẩm → đơn / sản phẩm / người bán,
thanh toán và review → đơn).

Vì có chủ đích thêm ca đặc biệt và chia đều theo tháng, **phân phối của bộ mẫu khác bộ gốc**
(ví dụ tỷ lệ giao trễ 4,8% so với 6,8%), nên không dùng bộ mẫu để phân tích.

Tạo lại bộ mẫu:

```bash
python -m src.etl.make_sample --raw-dir data/raw --out-dir data/sample
```
