"""
Nạp 4 fact: chạy các file SQL 2x trong src/etl/sql (20: tra khóa chung theo đơn, 21-24: các fact).
Chạy sau load_dimensions, trên cùng kết nối (cùng giao dịch); được gọi từ run_etl.
"""

from pathlib import Path
from src.common.db import count_rows, execute_sql_file

SQL_DIR = Path(__file__).parent / "sql"
FACTS = ["fact_sales", "fact_order_fulfillment", "fact_payment", "fact_review"]

def load_facts(conn, run_id: int) -> dict[str, int]:
    settings = {"etl.run_id": run_id}
    for path in sorted(SQL_DIR.glob("2*.sql")):
        execute_sql_file(conn, path, settings)
    return count_rows(conn, "dw", FACTS)
