"""Giao diện truy vấn SQL tự do (chỉ đọc) cho dashboard.

An toàn: chỉ nhận 1 câu SELECT / WITH, chạy trong giao dịch READ ONLY có giới hạn thời gian,
tự cắt số dòng trả về. Không thay thế phân quyền DB; môi trường thật nên dùng user chỉ có quyền SELECT.

Phụ trách: P2
"""
import re
from pathlib import Path

import pandas as pd

QUERIES_DIR = Path(__file__).parent / "queries"
MAX_ROWS = 5000
TIMEOUT_MS = 15000


def strip_comments(sql: str) -> str:
    return re.sub(r"--[^\n]*|/\*.*?\*/", "", sql, flags=re.DOTALL)


def split_statements(sql: str) -> list[str]:
    """Tách file .sql thành từng câu lệnh."""
    parts = [p.strip() for p in re.split(r";\s*(?:\n|$)", sql)]
    return [p for p in parts if strip_comments(p).strip()]


def validate_readonly(sql: str) -> str:
    """Trả về câu SQL đã làm sạch; ném ValueError nếu không phải 1 câu SELECT / WITH."""
    body = strip_comments(sql).strip().rstrip(";").strip()
    if not body:
        raise ValueError("Câu truy vấn rỗng.")
    if ";" in body:
        raise ValueError("Chỉ cho phép 1 câu lệnh mỗi lần chạy.")
    if not re.match(r"(?is)^(select|with)\b", body):
        raise ValueError("Chỉ cho phép câu lệnh SELECT / WITH.")
    return body


def run_readonly(engine, sql: str) -> pd.DataFrame:
    body = validate_readonly(sql)
    conn = engine.raw_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SET TRANSACTION READ ONLY")
            cur.execute(f"SET LOCAL statement_timeout = {TIMEOUT_MS}")
            cur.execute(body)
            cols = [c.name for c in cur.description]
            rows = cur.fetchmany(MAX_ROWS)
        return pd.DataFrame(rows, columns=cols)
    finally:
        conn.rollback()
        conn.close()


def load_example_queries() -> dict[str, str]:
    """Các truy vấn mẫu trong src/olap/queries: {'02_rollup · #1': sql, ...}."""
    examples = {}
    for path in sorted(QUERIES_DIR.glob("*.sql")):
        stmts = split_statements(path.read_text(encoding="utf-8"))
        for i, stmt in enumerate(stmts, 1):
            label = path.stem if len(stmts) == 1 else f"{path.stem} · câu {i}"
            examples[label] = stmt
    return examples
