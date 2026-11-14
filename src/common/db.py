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


def execute_sql_file(conn, path: str | Path, settings: dict[str, object] | None = None) -> bool:
    """Chạy nguyên văn một file SQL trên kết nối psycopg2 có sẵn, KHÔNG commit (người gọi quyết định).

    Không dùng sqlalchemy.text() vì nó coi ':ten' là tham số và có thể làm hỏng câu lệnh.
    settings: biến cấu hình cho file SQL, vd. {"etl.run_id": 5}; trong SQL đọc bằng
    current_setting('etl.run_id'). Biến tồn tại tới hết giao dịch hiện tại.
    Trả về False nếu file chưa có câu lệnh nào.
    """
    sql = Path(path).read_text(encoding="utf-8")
    if not has_statements(sql):
        return False
    with conn.cursor() as cur:
        for name, value in (settings or {}).items():
            cur.execute("SELECT set_config(%s, %s, true)", (name, str(value)))
        cur.execute(sql)
    return True


def run_sql_file(engine: Engine, path: str | Path, settings: dict[str, object] | None = None) -> bool:
    """Chạy một file SQL trong giao dịch riêng (mở kết nối, chạy, commit). Dùng cho init_db."""
    conn = engine.raw_connection()
    try:
        ran = execute_sql_file(conn, path, settings)
        conn.commit()
    finally:
        conn.close()
    return ran


def count_rows(conn, schema: str, tables: list[str]) -> dict[str, int]:
    """Đếm số dòng từng bảng, trả về {tên bảng: số dòng}."""
    counts = {}
    with conn.cursor() as cur:
        for table in tables:
            cur.execute(f"SELECT count(*) FROM {schema}.{table}")
            counts[table] = cur.fetchone()[0]
    return counts
