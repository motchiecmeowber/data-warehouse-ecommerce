"""Đọc 9 file CSV nguồn vào dict {tên bảng: DataFrame} để khảo sát."""
import pandas as pd

from src.common.config import RAW_DATA_DIR

pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 50)


def load_all() -> dict[str, pd.DataFrame]:
    tables = {}
    for path in sorted(RAW_DATA_DIR.glob("*.csv")):
        name = path.stem.replace("olist_", "").replace("_dataset", "")
        tables[name] = pd.read_csv(path)
    if not tables:
        raise FileNotFoundError(f"Không thấy file CSV nào trong {RAW_DATA_DIR}")
    return tables
