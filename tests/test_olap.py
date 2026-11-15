"""Kiểm thử lớp OLAP: bộ lọc, SQL chỉ đọc, DSS (không cần DB) và các view, truy vấn mẫu (cần DB đã chạy ETL và build).

Phụ trách: P2
"""
import numpy as np
import pandas as pd
import pytest
from sqlalchemy import text

from src.olap import console
from src.olap.cube import Filters, aggregate
from src.olap.dss_baseline import late_rate_curve, recommend_days, sensitivity


# ---------- không cần DB ----------
def test_filters_where_uses_bind_params_only():
    where, params = Filters(month_from="2017-01", states=["SP"], categories=["toys"]).where(categories=True)
    assert "toys" not in where and "SP" not in where          # giá trị không bị nhúng vào SQL
    assert params == {"month_from": "2017-01", "states": ["SP"], "categories": ["toys"]}
    assert where.endswith("is_valid_sale")


def test_filters_empty_and_prefix():
    assert Filters(valid_only=False).where() == ("", {})
    where, _ = Filters(month_to="2018-01").where(prefix="o.")
    assert "o.year_month <= :month_to" in where and "o.is_valid_sale" in where


def test_aggregate_rejects_unknown_dimension():
    with pytest.raises(ValueError):
        aggregate(None, ["year; DROP TABLE x"], [], "revenue", Filters())
    with pytest.raises(ValueError):
        aggregate(None, ["year"], [], "not_a_measure", Filters())


@pytest.mark.parametrize("sql", ["SELECT 1", "  with a as (select 1) select * from a;", "-- c\nSELECT 1"])
def test_console_accepts_select(sql):
    assert console.validate_readonly(sql)


@pytest.mark.parametrize("sql", ["", "DROP TABLE dw.dim_date", "DELETE FROM dw.fact_sales", "SELECT 1; DROP TABLE x",
                                 "UPDATE dw.dim_date SET year = 1", "/* SELECT */ INSERT INTO x VALUES (1)"])
def test_console_rejects_non_select(sql):
    with pytest.raises(ValueError):
        console.validate_readonly(sql)


def test_example_queries_are_all_loadable():
    examples = console.load_example_queries()
    assert len(examples) >= 15
    assert all(console.validate_readonly(sql) for sql in examples.values())


def test_dss_recommend_matches_quantile():
    df = pd.DataFrame({"delivery_days": np.arange(1, 101, dtype=float), "promised_days": 20.0,
                       "is_late": [False] * 90 + [True] * 10, "review_score": [5.0] * 90 + [1.0] * 10})
    assert recommend_days(df, 0.10) == 90          # 10% đơn giao > 90 ngày
    assert recommend_days(df.head(10), 0.05) is None  # quá ít đơn
    curve = late_rate_curve(df, range(1, 101))
    assert curve["late_rate"].is_monotonic_decreasing
    assert curve.loc[curve.promise_days == 100, "late_rate"].iloc[0] == 0
    assert sensitivity(df, [0.05, 0.10])["Số ngày hẹn gợi ý"].tolist() == [95, 90]


# ---------- cần DB ----------
@pytest.fixture(scope="module")
def engine():
    from src.common.db import get_engine
    try:
        eng = get_engine()
        with eng.connect() as conn:
            n = conn.execute(text("SELECT count(*) FROM olap.mv_sales_cube")).scalar()
    except Exception as e:
        pytest.skip(f"Chưa có DB / view olap: {type(e).__name__}")
    if not n:
        pytest.skip("olap rỗng: chạy ETL rồi python -m src.olap.build")
    return eng


def test_every_example_query_runs(engine):
    for label, sql in console.load_example_queries().items():
        df = console.run_readonly(engine, sql)
        assert df is not None, label


def test_flat_views_do_not_change_grain(engine):
    """View không được làm tăng hoặc mất dòng so với fact."""
    with engine.connect() as conn:
        pairs = [("dw.fact_sales", "olap.v_sales"), ("dw.fact_order_fulfillment", "olap.v_fulfillment"),
                 ("dw.fact_payment", "olap.v_payment"), ("dw.fact_review", "olap.v_review")]
        for fact, view in pairs:
            a = conn.execute(text(f"SELECT count(*) FROM {fact}")).scalar()
            b = conn.execute(text(f"SELECT count(*) FROM {view}")).scalar()
            assert a == b, f"{view}: {b} dòng, {fact}: {a} dòng"


def test_materialized_views_reconcile_with_facts(engine):
    """Tổng trong materialized view phải khớp fact."""
    with engine.connect() as conn:
        q = lambda s: conn.execute(text(s)).scalar()
        assert q("SELECT sum(revenue) FROM olap.mv_sales_cube") == q("SELECT sum(item_revenue) FROM dw.fact_sales")
        assert q("SELECT sum(orders) FROM olap.mv_delivery_cube") == q("SELECT count(*) FROM dw.fact_order_fulfillment")
        assert q("SELECT sum(late_orders) FROM olap.mv_delivery_cube") == \
            q("SELECT count(*) FROM dw.fact_order_fulfillment WHERE is_late")


def test_rollup_grand_total_equals_sum_of_months(engine):
    with engine.connect() as conn:
        total = conn.execute(text("""
            SELECT sum(item_revenue) FROM olap.v_sales WHERE is_valid_sale""")).scalar()
        grand = conn.execute(text("""
            SELECT sum(item_revenue) FROM olap.v_sales WHERE is_valid_sale GROUP BY ROLLUP (year, quarter, month)
            HAVING grouping(year, quarter, month) = 7""")).scalar()
        assert total == grand
