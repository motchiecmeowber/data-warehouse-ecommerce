"""Chạy lần lượt các file DDL trong src/sql để khởi tạo database.

Chạy: python -m src.sql.init_db
"""
from pathlib import Path

from src.common.db import get_engine, run_sql_file

SQL_DIR = Path(__file__).parent

if __name__ == "__main__":
    engine = get_engine()
    for path in sorted(SQL_DIR.glob("*.sql")):
        ran = run_sql_file(engine, path)
        print(f"{'Ran ' if ran else 'Skip'} {path.name}" + ("" if ran else " (chưa có câu lệnh)"))
