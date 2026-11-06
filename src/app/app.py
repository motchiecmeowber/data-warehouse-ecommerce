"""Ứng dụng Streamlit: dashboard + DSS.

Chạy: streamlit run src/app/app.py
Phụ trách: B
"""
import sys
from pathlib import Path

import streamlit as st

# `streamlit run` chỉ thêm thư mục src/app vào sys.path; thêm thư mục gốc repo để import được `src.*`
ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

st.set_page_config(page_title="E-commerce DW & DSS", layout="wide")

pages = [
    st.Page("pages/1_Tong_quan.py", title="Tổng quan"),
    st.Page("pages/2_Logistics.py", title="Logistics"),
    st.Page("pages/3_Nguoi_ban.py", title="Người bán"),
    st.Page("pages/4_OLAP_explorer.py", title="OLAP explorer"),
    st.Page("pages/5_Mo_hinh_ML.py", title="Mô hình ML"),
    st.Page("pages/6_DSS_ngay_hen_giao.py", title="DSS ngày hẹn giao"),
]
st.navigation(pages).run()
