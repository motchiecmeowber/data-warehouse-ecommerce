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
st.logo(str(ROOT_DIR / "src" / "app" / "assets" / "logo.svg"), size="large")
# Tiêu đề nhóm trong menu: chữ in hoa, đậm, màu chủ đạo
st.html("""<style>
[data-testid="stNavSectionHeader"] {
    color: #2563EB; font-weight: 700; font-size: 0.78rem;
    text-transform: uppercase; letter-spacing: 0.06em; margin-top: 0.75rem;
}
</style>""")

pages = {
    "Phân tích dữ liệu": [
        st.Page("pages/1_Tong_quan.py", title="Tổng quan", icon=":material/dashboard:"),
        st.Page("pages/2_Logistics.py", title="Logistics", icon=":material/local_shipping:"),
        st.Page("pages/3_Nguoi_ban.py", title="Người bán", icon=":material/storefront:"),
        st.Page("pages/4_OLAP_explorer.py", title="OLAP explorer", icon=":material/view_in_ar:"),
    ],
    "Mô hình & hỗ trợ quyết định": [
        st.Page("pages/5_Mo_hinh_ML.py", title="Phân cụm khách hàng", icon=":material/groups:"),
        st.Page("pages/6_DSS_ngay_hen_giao.py", title="DSS ngày hẹn giao", icon=":material/lightbulb:"),
        st.Page("pages/7_What_if_ML.py", title="What-if rủi ro trễ (ML)", icon=":material/model_training:"),
    ],
}
st.navigation(pages).run()
