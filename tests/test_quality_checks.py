"""Kiểm tra quality check của ETL (cần DB đã chạy ETL).

Phụ trách: A
"""
import pytest
from sqlalchemy import text

from src.etl.quality_checks import run_quality_checks

CATEGORIES = {"completeness", "reconciliation", "referential", "scd2", "validity"}


@pytest.fixture(scope="module")
def engine():
    from src.common.db import get_engine
    try:
        eng = get_engine()
        with eng.connect() as conn:
            conn.execute(text("SELECT 1 FROM etl_log.run_history LIMIT 1"))
    except Exception as e:
        pytest.skip(f"Chưa có DB: {type(e).__name__}")
    return eng


@pytest.fixture(scope="module")
def run_id(engine):
    with engine.connect() as conn:
        rid = conn.execute(text("SELECT max(run_id) FROM etl_log.run_history WHERE status = 'success'")).scalar()
    if rid is None:
        pytest.skip("Chưa có lần chạy ETL thành công: python -m src.etl.run_etl")
    return rid


def test_last_successful_run_passed_every_check(engine, run_id):
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT category, check_name, expected, actual, passed FROM etl_log.quality_check "
                                 "WHERE run_id = :r"), {"r": run_id}).all()
    assert {r.category for r in rows} == CATEGORIES
    failed = [f"[{r.category}] {r.check_name}: mong đợi {r.expected}, thực tế {r.actual}" for r in rows if not r.passed]
    assert not failed, failed


def test_current_warehouse_still_passes(engine, run_id):
    # Chạy lại các phép kiểm tra trên kho hiện tại rồi rollback, không ghi gì vào etl_log
    conn = engine.raw_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT max(check_id) FROM etl_log.quality_check")
            last = cur.fetchone()[0] or 0
        run_quality_checks(conn, run_id)
        with conn.cursor() as cur:
            cur.execute("SELECT category, check_name, passed FROM etl_log.quality_check WHERE check_id > %s", (last,))
            new = cur.fetchall()
    finally:
        conn.rollback()
        conn.close()
    assert {c for c, _, _ in new} == CATEGORIES
    assert all(passed for _, _, passed in new), [name for _, name, passed in new if not passed]
