"""Cắt bộ dữ liệu mẫu từ data/raw sang data/sample, giữ đúng quan hệ khóa giữa 9 file.

- Lấy ngẫu nhiên (có seed) một số đơn đã giao mỗi tháng trong giai đoạn 2017-01 → 2018-08.
- Thêm một ít "ca đặc biệt" để ETL có dữ liệu bẩn mà xử lý: các trạng thái khác `delivered`,
  đơn không có dòng sản phẩm, mốc thời gian bất thường, danh mục chưa có bản dịch,
  đơn ở giai đoạn thưa (2016, 09–10/2018).
- Kéo theo toàn bộ dòng liên quan: khách, sản phẩm của đơn, người bán, thanh toán, review.
- Geolocation: giữ tối đa N dòng cho mỗi mã bưu điện được dùng, cộng các điểm nằm ngoài Brazil.
- Mỗi dòng được chép NGUYÊN VĂN từ file gốc (giữ cách quote, BOM, xuống dòng).

Chỉ dùng thư viện chuẩn. Chạy (ở thư mục gốc repo):
    python -m src.etl.make_sample --raw-dir data/raw --out-dir data/sample

Phụ trách: A
"""
import argparse
import csv
import random
import shutil
from collections import defaultdict
from pathlib import Path

FILES = {
    "orders": "olist_orders_dataset.csv",
    "items": "olist_order_items_dataset.csv",
    "payments": "olist_order_payments_dataset.csv",
    "reviews": "olist_order_reviews_dataset.csv",
    "customers": "olist_customers_dataset.csv",
    "sellers": "olist_sellers_dataset.csv",
    "products": "olist_products_dataset.csv",
    "geolocation": "olist_geolocation_dataset.csv",
    "translation": "product_category_name_translation.csv",
}
BRAZIL_BBOX = (-33.8, 5.3, -74.0, -34.7)  # lat_min, lat_max, lng_min, lng_max


def read_records(path: Path):
    """Trả về (header_text, [(row_dict, raw_text), ...]); raw_text giữ nguyên văn kể cả field nhiều dòng."""
    with open(path, encoding="utf-8", newline="") as f:
        lines = iter(f)
        buffer = []

        def tracking():
            for line in lines:
                buffer.append(line)
                yield line

        reader = csv.reader(tracking())
        header = next(reader)
        header_text = "".join(buffer)
        buffer.clear()
        records = []
        for row in reader:
            records.append((dict(zip([h.lstrip("﻿") for h in header], row)), "".join(buffer)))
            buffer.clear()
    return header_text, records


def write_records(path: Path, header_text: str, raws) -> None:
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(header_text)
        for raw in raws:
            f.write(raw)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--raw-dir", default="data/raw")
    parser.add_argument("--out-dir", default="data/sample")
    parser.add_argument("--orders-per-month", type=int, default=70)
    parser.add_argument("--edge-cases-per-group", type=int, default=8)
    parser.add_argument("--geo-rows-per-zip", type=int, default=5)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    raw_dir, out_dir = Path(args.raw_dir), Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    rng = random.Random(args.seed)
    data = {k: read_records(raw_dir / v) for k, v in FILES.items() if k != "translation"}

    orders = [r for r, _ in data["orders"][1]]
    items_by_order = defaultdict(list)
    for r, _ in data["items"][1]:
        items_by_order[r["order_id"]].append(r)

    def pick(candidates, k):
        candidates = sorted(candidates)
        return set(rng.sample(candidates, min(k, len(candidates))))

    # 1) Đơn đã giao, chia đều theo tháng
    by_month = defaultdict(list)
    for o in orders:
        month = o["order_purchase_timestamp"][:7]
        if o["order_status"] == "delivered" and "2017-01" <= month <= "2018-08":
            by_month[month].append(o["order_id"])
    selected = set()
    for ids in by_month.values():
        selected |= pick(ids, args.orders_per_month)

    # 2) Ca đặc biệt
    k = args.edge_cases_per_group
    translated = {r["product_category_name"] for r, _ in read_records(raw_dir / FILES["translation"])[1]}
    untranslated_products = {
        r["product_id"] for r, _ in data["products"][1]
        if r["product_category_name"] and r["product_category_name"] not in translated
    }
    edge_groups = {
        "status_khac_delivered": defaultdict(list),
        "khong_co_san_pham": [o["order_id"] for o in orders if o["order_id"] not in items_by_order],
        "giao_van_chuyen_truoc_khi_duyet": [
            o["order_id"] for o in orders
            if o["order_delivered_carrier_date"] and o["order_approved_at"]
            and o["order_delivered_carrier_date"] < o["order_approved_at"]
        ],
        "danh_muc_chua_dich": [
            oid for oid, its in items_by_order.items() if any(i["product_id"] in untranslated_products for i in its)
        ],
        "giai_doan_thua": [
            o["order_id"] for o in orders
            if not ("2017-01" <= o["order_purchase_timestamp"][:7] <= "2018-08")
        ],
    }
    for o in orders:
        if o["order_status"] != "delivered":
            edge_groups["status_khac_delivered"][o["order_status"]].append(o["order_id"])
    for name, group in edge_groups.items():
        if isinstance(group, dict):
            for ids in group.values():
                selected |= pick(ids, k)
        else:
            selected |= pick(group, k)

    # 3) Kéo theo các bảng liên quan
    keep = {"orders": selected}
    keep["customers"] = {r["customer_id"] for r, _ in data["orders"][1] if r["order_id"] in selected}
    sample_items = [r for r, _ in data["items"][1] if r["order_id"] in selected]
    keep["products"] = {r["product_id"] for r in sample_items}
    keep["sellers"] = {r["seller_id"] for r in sample_items}

    key_of = {
        "orders": lambda r: r["order_id"] in keep["orders"],
        "items": lambda r: r["order_id"] in keep["orders"],
        "payments": lambda r: r["order_id"] in keep["orders"],
        "reviews": lambda r: r["order_id"] in keep["orders"],
        "customers": lambda r: r["customer_id"] in keep["customers"],
        "products": lambda r: r["product_id"] in keep["products"],
        "sellers": lambda r: r["seller_id"] in keep["sellers"],
    }
    for name, keep_row in key_of.items():
        header, records = data[name]
        raws = [raw for r, raw in records if keep_row(r)]
        write_records(out_dir / FILES[name], header, raws)
        print(f"{FILES[name]}: {len(raws)} rows")

    # 4) Geolocation
    zips = {r["customer_zip_code_prefix"] for r, _ in data["customers"][1] if r["customer_id"] in keep["customers"]}
    zips |= {r["seller_zip_code_prefix"] for r, _ in data["sellers"][1] if r["seller_id"] in keep["sellers"]}
    lat_min, lat_max, lng_min, lng_max = BRAZIL_BBOX
    per_zip = defaultdict(int)
    geo_raws = []
    header, records = data["geolocation"]
    for r, raw in records:
        lat, lng = float(r["geolocation_lat"]), float(r["geolocation_lng"])
        outside = not (lat_min <= lat <= lat_max and lng_min <= lng <= lng_max)
        z = r["geolocation_zip_code_prefix"]
        if outside or (z in zips and per_zip[z] < args.geo_rows_per_zip):
            per_zip[z] += 1
            geo_raws.append(raw)
    write_records(out_dir / FILES["geolocation"], header, geo_raws)
    print(f"{FILES['geolocation']}: {len(geo_raws)} rows")

    # 5) Bảng dịch danh mục: nhỏ, chép nguyên file
    shutil.copyfile(raw_dir / FILES["translation"], out_dir / FILES["translation"])
    print(f"{FILES['translation']}: copied")


if __name__ == "__main__":
    main()
