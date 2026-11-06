"""Kết nối PostgreSQL (local Docker hoặc Neon, tùy DATABASE_URL trong .env)."""
import re
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from src.common.config import DATABASE_URL


def get_engine() -> Engine:
    if not DATABASE_URL:
        raise RuntimeError("Chưa cấu hình DATABASE_URL trong file .env (xem .env.example)")
    return create_engine(DATABASE_URL, pool_pre_ping=True)


def has_statements(sql: str) -> bool:
    """File chỉ có comment thì Postgres báo lỗi 'empty query', nên cần bỏ qua."""
    without_comments = re.sub(r"--[^\n]*|/\*.*?\*/", "", sql, flags=re.DOTALL)
    return bool(without_comments.strip().strip(";").strip())


def run_sql_file(engine: Engine, path: str | Path) -> bool:
    """Chạy nguyên văn một file SQL qua cursor của psycopg2.

    Không dùng sqlalchemy.text() vì nó coi ':ten' là tham số và có thể làm hỏng câu lệnh.
    Trả về False nếu file chưa có câu lệnh nào.
    """
    sql = Path(path).read_text(encoding="utf-8")
    if not has_statements(sql):
        return False
    conn = engine.raw_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()
    finally:
        conn.close()
    return True
