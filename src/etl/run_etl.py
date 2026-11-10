"""
Chạy pipeline ETL: extract -> nạp dimension -> nạp fact -> kiểm tra chất lượng.
Mỗi lần chạy ghi 1 dòng vào etl_log.run_history; dòng dữ liệu lỗi ghi vào etl_log.error_queue.
"""

import argparse

from sqlalchemy import text

from src.common.config import RAW_DATA_DIR
from src.common.db import get_engine
from src.etl.extract import extract
from src.etl.load_dimensions import load_dimensions
from src.etl.load_facts import load_facts
from src.etl.quality_checks import run_quality_checks

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


def print_checks(checks: list[tuple]) -> None:
    print("\nquality_check")
    for category, check_name, expected, actual, passed in checks:
        mark = "ĐẠT     " if passed else "KHÔNG ĐẠT"
        print(f"  {mark} [{category}] {check_name}: mong đợi {expected}, thực tế {actual}")


def transform_and_load(engine, run_id: int) -> list[tuple]:
    # Nạp dimension, fact và kiểm tra chất lượng trong 1 giao dịch: lỗi ở bất kỳ bước nào thì
    # rollback toàn bộ, kho giữ nguyên dữ liệu của lần chạy thành công trước đó
    conn = engine.raw_connection()
    try:
        print_counts("Dimension -> dw", load_dimensions(conn, run_id))
        print_counts("Fact -> dw", load_facts(conn, run_id))
        checks = run_quality_checks(conn, run_id)
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()
    return checks


def main() -> None:
    parser = argparse.ArgumentParser(description="Chạy pipeline ETL")
    parser.add_argument("--data-dir", default=RAW_DATA_DIR, help="thư mục chứa 9 file CSV (mặc định: data/raw)")
    args = parser.parse_args()

    engine = get_engine()
    run_id = start_run(engine, str(args.data_dir))
    print(f"run_id = {run_id}")
    try:
        print_counts("Extract -> staging", extract(engine, args.data_dir))
        checks = transform_and_load(engine, run_id)
    except BaseException as e:  # BaseException: bắt cả Ctrl+C để không kẹt trạng thái running
        finish_run(engine, run_id, "failed", (str(e) or type(e).__name__)[:1000])
        raise
    print_errors(engine, run_id)
    print_checks(checks)

    # Có kiểm tra không đạt: dữ liệu vẫn giữ, nhưng lần chạy ghi failed và lệnh trả mã lỗi 1
    failed = [check_name for _, check_name, _, _, passed in checks if not passed]
    if failed:
        finish_run(engine, run_id, "failed", "Kiểm tra chất lượng không đạt: " + "; ".join(failed))
        raise SystemExit(1)
    finish_run(engine, run_id, "success")


if __name__ == "__main__":
    main()