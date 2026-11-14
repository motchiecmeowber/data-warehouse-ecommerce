"""Hiển thị số liệu đánh giá mô hình (reports/metrics) và biểu đồ (reports/figures) do P3 ghi ra.

Phụ trách: P2 (hiển thị), P3 (nội dung)
"""
import json

import pandas as pd
import streamlit as st

from src.common.config import ROOT_DIR

METRICS_DIR = ROOT_DIR / "reports" / "metrics"
FIGURES_DIR = ROOT_DIR / "reports" / "figures"

st.title("Mô hình ML")
st.caption("Số liệu đánh giá và biểu đồ của các mô hình dự đoán rủi ro giao trễ (nhóm P3 ghi vào reports/).")

metric_files = sorted(p for p in METRICS_DIR.glob("*") if p.suffix in {".csv", ".json"})
figure_files = sorted(FIGURES_DIR.glob("*.png"))

if not metric_files and not figure_files:
    st.info("Chưa có kết quả mô hình. Sau khi chạy `python -m src.ml.train`, các file số liệu trong "
            "`reports/metrics/` và biểu đồ trong `reports/figures/` sẽ hiển thị ở đây.")
    st.stop()

for path in metric_files:
    st.subheader(path.stem.replace("_", " ").capitalize())
    try:
        if path.suffix == ".csv":
            st.dataframe(pd.read_csv(path), hide_index=True, alt=f"Số liệu mô hình: {path.stem}")
        else:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and all(isinstance(v, (int, float)) for v in data.values()):
                cols = st.columns(min(len(data), 5))
                for i, (k, v) in enumerate(data.items()):
                    cols[i % len(cols)].metric(k, f"{v:.4g}")
            else:
                st.json(data)
    except Exception as e:
        st.warning(f"Không đọc được {path.name}: {e}")

if figure_files:
    st.subheader("Biểu đồ")
    cols = st.columns(2)
    for i, path in enumerate(figure_files):
        cols[i % 2].image(str(path), caption=path.stem.replace("_", " "), width="stretch",
                         alt=f"Biểu đồ mô hình: {path.stem.replace('_', ' ')}")
