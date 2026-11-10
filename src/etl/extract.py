"""
Extract: nạp 9 file CSV nguồn và 2 file tham chiếu vào schema staging, giữ nguyên văn mọi giá trị (kiểu TEXT).
Chạy (ở thư mục gốc): python -m src.etl.extract [--data-dir data/sample]
"""
import argparse
import csv

from pathlib import Path
from src.common.config import RAW_DATA_DIR, ROOT_DIR, load_yaml
from src.common.db import get_engine

def read_header(path: Path) -> list[str]:
    with open(path, encoding="utf-8-sig", newline="") as f:
        return next(csv.reader(f))

def load_table(conn, table: str, path: Path) -> int:
    columns = ", ".join(f'"{name}"' for name in read_header(path))
    copy_sql = f"COPY staging.{table} ({columns}) FROM STDIN WITH (FORMAT csv, HEADER true)"
    try:
        with conn.cursor() as cur:
            cur.execute(f"TRUNCATE staging.{table}")
            with open(path, encoding="utf-8-sig", newline="") as f:
                cur.copy_expert(copy_sql, f)
            cur.execute(f"SELECT count(*) FROM staging.{table}")
            rows = cur.fetchone()[0]
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return rows

def extract(engine, data_dir: Path = RAW_DATA_DIR) -> dict[str, int]:
    config = load_yaml("etl.yaml")
    files = {table: Path(data_dir) / name for table, name in config["raw_files"].items()}
    reference_dir = ROOT_DIR / config["reference_dir"]
    files |= {table: reference_dir / name for table, name in config["reference_files"].items()}

    counts = {}
    conn = engine.raw_connection()
    try:
        for table, path in files.items():
            counts[table] = load_table(conn, table, path)
    finally:
        conn.close()
    return counts

def main() -> None:
    parser = argparse.ArgumentParser(description="Nạp CSV vào schema staging")
    parser.add_argument("--data-dir", default=RAW_DATA_DIR, help="thư mục chứa 9 file CSV (mặc định: data/raw)")
    args = parser.parse_args()

    counts = extract(get_engine(), args.data_dir)
    for table, rows in counts.items():
        print(f"staging.{table:<35} {rows:>9,} dòng")


if __name__ == "__main__":
    main()