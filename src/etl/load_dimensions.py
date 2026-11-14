"""
Nạp 7 dimension: xóa sạch schema dw, chèn lại dòng Unknown, rồi chạy các file SQL biến đổi trong src/etl/sql.
Được gọi từ run_etl, chạy trên kết nối chung (chưa commit) để cả lần nạp là 1 giao dịch.
"""

from pathlib import Path
from src.common.config import ROOT_DIR, load_yaml
from src.common.db import count_rows, execute_sql_file

SQL_DIR = Path(__file__).parent / "sql"
DDL_DIMENSIONS = ROOT_DIR / "src" / "sql" / "02_dimensions.sql"
DIMENSIONS = [
    "dim_date", "dim_geography", "dim_customer", "dim_seller",
    "dim_product", "dim_order_status", "dim_payment_type",
]
FACTS = ["fact_sales", "fact_order_fulfillment", "fact_payment", "fact_review"]


def reset_dw(conn) -> None:
    # Nạp lại toàn bộ (đặt lại bộ đếm surrogate key về 1)
    tables = ", ".join(f"dw.{t}" for t in FACTS + DIMENSIONS)
    with conn.cursor() as cur:
        cur.execute(f"TRUNCATE {tables} RESTART IDENTITY")
    execute_sql_file(conn, DDL_DIMENSIONS) # Chạy lại DDL dimension (chèn dòng Unknown (-1))


def load_dimensions(conn, run_id: int) -> dict[str, int]:
    reset_dw(conn)
    bbox = load_yaml("etl.yaml")["brazil_bbox"]
    settings = {"etl.run_id": run_id} | {f"etl.{name}": value for name, value in bbox.items()}
    for path in sorted(SQL_DIR.glob("0*.sql")) + sorted(SQL_DIR.glob("1*.sql")):
        execute_sql_file(conn, path, settings)
    return count_rows(conn, "dw", DIMENSIONS)
