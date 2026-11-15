"""Phân cụm khách hàng trên toàn bộ đơn hợp lệ trong khoảng năm đã chọn."""

import pandas as pd
import streamlit as st
from sqlalchemy.exc import SQLAlchemyError

from src.common.db import get_engine
from src.ml.kmean import run_kmeans


st.title("Phân cụm khách hàng")
st.caption("K-Means: 4 cụm, lọc theo ngày mua hàng, bao gồm cả năm kết thúc.")

with st.form("customer_clustering"):
    start_year = st.number_input(
        "Từ năm", min_value=1, max_value=9998, value=2017, step=1
    )
    end_year = st.number_input(
        "Đến năm", min_value=1, max_value=9998, value=2018, step=1
    )
    submitted = st.form_submit_button("Phân cụm khách hàng")

if submitted:
    st.session_state.pop("customer_segments", None)
    if start_year > end_year:
        st.error("Năm bắt đầu phải nhỏ hơn hoặc bằng năm kết thúc.")
    else:
        try:
            engine = get_engine()
            try:
                with st.spinner("Đang đọc dữ liệu và phân cụm..."):
                    path = run_kmeans(engine, start_year, end_year)
                    result = pd.read_csv(
                        path, dtype={"customer_unique_id": "string"}
                    )
            finally:
                engine.dispose()
        except (ValueError, RuntimeError, SQLAlchemyError, OSError):
            st.error(
                "Không thể phân cụm. Kiểm tra kết nối database, dữ liệu "
                "và ít nhất 4 hồ sơ RFM khác nhau trong khoảng năm đã chọn."
            )
        else:
            st.session_state["customer_segments"] = (
                start_year, end_year, result
            )

if "customer_segments" in st.session_state:
    trained_start, trained_end, result = st.session_state["customer_segments"]
    st.subheader(f"Kết quả {trained_start}–{trained_end}")
    st.metric("Số khách hàng", len(result))
    st.bar_chart(result["kmeans_segment"].value_counts())
    st.dataframe(result, hide_index=True)
