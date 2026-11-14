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
