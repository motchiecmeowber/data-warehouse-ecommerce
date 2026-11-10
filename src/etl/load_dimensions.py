"""
Nạp 7 dimension: xóa sạch schema dw, chèn lại dòng Unknown, rồi chạy các file SQL biến đổi trong src/etl/sql.
Được gọi từ run_etl (cần run_id để ghi error_queue).
"""

from pathlib import Path
from sqlalchemy import text
from src.common.config import ROOT_DIR, load_yaml
from src.common.db import run_sql_file

SQL_DIR = Path(__file__).parent / "sql"
DDL_DIMENSIONS = ROOT_DIR / "src" / "sql" / "02_dimensions.sql"
DIMENSIONS = [
    "dim_date", "dim_geography", "dim_customer", "dim_seller",
    "dim_product", "dim_order_status", "dim_payment_type",
]
FACTS = ["fact_sales", "fact_order_fulfillment", "fact_payment", "fact_review"]


def reset_dw(engine) -> None:
    # Nạp lại toàn bộ (đặt lại bộ đếm surrogate key về 1)
    tables = ", ".join(f"dw.{t}" for t in FACTS + DIMENSIONS)
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY"))
    run_sql_file(engine, DDL_DIMENSIONS) # Chạy lại DDL dimension (chèn dòng Unknown (-1))


def load_dimensions(engine, run_id: int) -> dict[str, int]:
    reset_dw(engine)
    bbox = load_yaml("etl.yaml")["brazil_bbox"]
    settings = {"etl.run_id": run_id} | {f"etl.{name}": value for name, value in bbox.items()}
    for path in sorted(SQL_DIR.glob("0*.sql")) + sorted(SQL_DIR.glob("1*.sql")):
        run_sql_file(engine, path, settings)

    with engine.connect() as conn:
        return {t: conn.execute(text(f"SELECT count(*) FROM dw.{t}")).scalar() for t in DIMENSIONS}