"""
Chạy pipeline ETL: extract -> nạp dimension (nạp fact, kiểm tra chất lượng: bổ sung sau).
Mỗi lần chạy ghi 1 dòng vào etl_log.run_history; dòng dữ liệu lỗi ghi vào etl_log.error_queue.
"""

import argparse

from sqlalchemy import text

from src.common.config import RAW_DATA_DIR
from src.common.db import get_engine
from src.etl.extract import extract
from src.etl.load_dimensions import load_dimensions


def start_run(engine, data_source: str) -> int:
    with engine.begin() as conn:
        return conn.execute(
            text("INSERT INTO etl_log.run_history (status, data_source) VALUES ('running', :source) RETURNING run_id"),
            {"source": data_source},
        ).scalar()


def finish_run(engine, run_id: int, status: str, message: str | None = None) -> None:
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE etl_log.run_history SET finished_at = now(), status = :status, message = :message "
                 "WHERE run_id = :run_id"),
            {"status": status, "message": message, "run_id": run_id},
        )


def print_counts(title: str, counts: dict[str, int]) -> None:
    print(f"\n{title}")
    for table, rows in counts.items():
        print(f"  {table:<35} {rows:>9,} dòng")


def print_errors(engine, run_id: int) -> None:
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT rule_code, source_table, count(*) FROM etl_log.error_queue "
                 "WHERE run_id = :run_id GROUP BY 1, 2 ORDER BY 1"),
            {"run_id": run_id},
        ).all()
    print("\nerror_queue")
    for rule_code, source_table, n in rows:
        print(f"  {rule_code} {source_table:<31} {n:>9,} dòng")
    if not rows:
        print("  (không có lỗi)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Chạy pipeline ETL")
    parser.add_argument("--data-dir", default=RAW_DATA_DIR, help="thư mục chứa 9 file CSV (mặc định: data/raw)")
    args = parser.parse_args()

    engine = get_engine()
    run_id = start_run(engine, str(args.data_dir))
    print(f"run_id = {run_id}")
    try:
        print_counts("Extract -> staging", extract(engine, args.data_dir))
        print_counts("Dimension -> dw", load_dimensions(engine, run_id))
    except Exception as e:
        finish_run(engine, run_id, "failed", str(e)[:1000])
        raise
    finish_run(engine, run_id, "success")
    print_errors(engine, run_id)


if __name__ == "__main__":
    main()