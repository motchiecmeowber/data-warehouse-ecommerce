"""
Kiểm tra chất lượng sau ETL: chạy các file SQL 3x trong src/etl/sql, kết quả ghi vào etl_log.quality_check.
Được gọi từ run_etl sau khi nạp fact, trên cùng kết nối (cùng giao dịch).
"""

from pathlib import Path
from src.common.db import execute_sql_file

SQL_DIR = Path(__file__).parent / "sql"

def run_quality_checks(conn, run_id: int) -> list[tuple]:
    for path in sorted(SQL_DIR.glob("3*.sql")):
        execute_sql_file(conn, path, {"etl.run_id": run_id})

    with conn.cursor() as cur:
        cur.execute(
            "SELECT category, check_name, expected, actual, passed FROM etl_log.quality_check "
            "WHERE run_id = %s ORDER BY check_id",
            (run_id,),
        )
        return cur.fetchall()
