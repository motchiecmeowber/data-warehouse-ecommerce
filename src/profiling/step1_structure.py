"""
Khảo sát bước 1 – Cấu trúc: số dòng, số cột, kiểu dữ liệu, vài dòng mẫu.
Chạy (ở thư mục gốc): python -m src.profiling.step1_structure
"""
import pandas as pd

from src.common.config import RAW_DATA_DIR
from src.profiling.load import load_all

if __name__ == "__main__":
    df = load_all()
    print(f"Thư mục dữ liệu: {RAW_DATA_DIR}\n")

    print("=== Số dòng, số cột ===")
    print(pd.DataFrame({name: {"so_dong": len(d), "so_cot": d.shape[1]} for name, d in df.items()}).T, "\n")

    print("=== Kiểu dữ liệu từng cột ===")
    for name, d in df.items():
        print(f"-- {name}")
        print(d.dtypes.to_string(), "\n")

    print("=== 3 dòng mẫu mỗi bảng ===")
    for name, d in df.items():
        print(f"-- {name}")
        print(d.head(3).to_string(), "\n")