"""Tạo (hoặc làm mới) các view và materialized view của schema olap.

Chạy:
    python -m src.olap.build            # tạo/ghi đè view + materialized view (chạy sau ETL)
    python -m src.olap.build --refresh  # chỉ REFRESH materialized view (sau mỗi lần ETL, schema không đổi)

Phụ trách: P2
"""
import argparse
from pathlib import Path

from src.common.db import get_engine, run_sql_file

VIEWS_DIR = Path(__file__).parent / "views"
MATERIALIZED_VIEWS = ["mv_sales_cube", "mv_delivery_cube", "mv_seller_scorecard"]


def build_views(engine) -> None:
    for path in sorted(VIEWS_DIR.glob("*.sql")):
        ran = run_sql_file(engine, path)
        print(f"{'Ran ' if ran else 'Skip'} {path.name}")


def refresh_materialized_views(engine) -> None:
    conn = engine.raw_connection()
    try:
        with conn.cursor() as cur:
            for name in MATERIALIZED_VIEWS:
                cur.execute(f"REFRESH MATERIALIZED VIEW olap.{name}")
                print(f"Refreshed olap.{name}")
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Tạo / làm mới view của schema olap")
    parser.add_argument("--refresh", action="store_true", help="chỉ REFRESH materialized view")
    args = parser.parse_args()
    engine = get_engine()
    if args.refresh:
        refresh_materialized_views(engine)
    else:
        build_views(engine)
