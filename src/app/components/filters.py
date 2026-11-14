"""Bộ lọc dùng chung ở sidebar (tháng, vùng, bang, danh mục, loại đơn)."""
import streamlit as st

from src.app.components.data import query
from src.olap.cube import Filters


def sidebar_filters(with_category: bool = False, key: str = "f") -> Filters:
    months = query("SELECT DISTINCT year_month FROM olap.mv_sales_cube ORDER BY 1")["year_month"].tolist()
    geo = query("SELECT DISTINCT customer_region, customer_state FROM olap.mv_sales_cube ORDER BY 1, 2")
    st.sidebar.header("Bộ lọc")
    m_from, m_to = st.sidebar.select_slider("Khoảng tháng", options=months, value=(months[0], months[-1]),
                                            key=f"{key}_months")
    regions = st.sidebar.multiselect("Vùng (khách hàng)", sorted(geo["customer_region"].unique()), key=f"{key}_reg",
                                     placeholder="Tất cả các vùng")
    state_opts = sorted(geo[geo["customer_region"].isin(regions)]["customer_state"].unique() if regions
                        else geo["customer_state"].unique())
    states = st.sidebar.multiselect("Bang (khách hàng)", state_opts, key=f"{key}_st", placeholder="Tất cả các bang")
    categories: list[str] = []
    if with_category:
        cats = query("SELECT DISTINCT category FROM olap.mv_sales_cube ORDER BY 1")["category"].tolist()
        categories = st.sidebar.multiselect("Danh mục sản phẩm", cats, key=f"{key}_cat", placeholder="Tất cả danh mục")
    valid_only = st.sidebar.checkbox("Chỉ tính đơn hợp lệ", value=True, key=f"{key}_valid",
                                     help="Loại các đơn bị hủy hoặc không có hàng")
    return Filters(month_from=m_from, month_to=m_to, regions=regions, states=states,
                   categories=categories, valid_only=valid_only)


def fmt_money(v) -> str:
    return "–" if v is None or v != v else f"R$ {v:,.0f}"


def fmt_pct(v, digits: int = 1) -> str:
    return "–" if v is None or v != v else f"{v * 100:.{digits}f}%"
