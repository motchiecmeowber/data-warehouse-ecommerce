"""Trang tổng quan bán hàng: doanh thu, số đơn, xu hướng theo thời gian.

Phụ trách: P2
"""
import streamlit as st

from src.app.components import charts
from src.app.components.data import query, require_olap
from src.app.components.filters import fmt_money, fmt_pct, sidebar_filters

st.title("Tổng quan bán hàng")
st.caption("Doanh thu, số đơn, giá trị đơn, tỷ lệ giao trễ và điểm review; xu hướng theo tháng, danh mục, bang và thanh toán.")
require_olap()
flt = sidebar_filters(with_category=True)

# KPI cấp đơn (mv_delivery_cube không có chiều danh mục)
where_d, p_d = flt.where()
k = query(f"""
    SELECT sum(revenue) AS revenue, sum(orders) AS orders, sum(freight) AS freight,
           sum(delivered_orders) AS delivered, sum(late_orders) AS late,
           sum(sum_delivery_days) / nullif(sum(n_delivery_days), 0) AS avg_days
    FROM olap.mv_delivery_cube {where_d}""", p_d).iloc[0]

where_r, p_r = flt.where(prefix="o.")
review = query(f"""
    SELECT avg(r.review_score) AS score
    FROM olap.v_review r JOIN olap.v_fulfillment o USING (order_id) {where_r}""", p_r).iloc[0, 0]

with st.container(horizontal=True):
    st.metric("Doanh thu", fmt_money(k.revenue), border=True)
    st.metric("Số đơn", f"{int(k.orders or 0):,}", border=True)
    st.metric("Giá trị đơn TB", fmt_money(k.revenue / k.orders if k.orders else None), border=True)
    st.metric("Phí vận chuyển / doanh thu", fmt_pct(k.freight / k.revenue if k.revenue else None), border=True)
    st.metric("Tỷ lệ giao trễ", fmt_pct(k.late / k.delivered if k.delivered else None), border=True,
              help="Trên các đơn đã giao: ngày khách nhận > ngày hẹn giao")
    st.metric("Điểm review TB", f"{review:.2f} / 5" if review is not None and review == review else "–", border=True)
if flt.categories:
    st.caption("Các chỉ số trên là cấp đơn hàng nên không lọc theo danh mục; biểu đồ doanh thu bên dưới có lọc.")

# --- Xu hướng
where_s, p_s = flt.where(categories=True)
trend = query(f"""
    SELECT year_month, sum(revenue) AS revenue, sum(units) AS units
    FROM olap.mv_sales_cube {where_s} GROUP BY year_month ORDER BY year_month""", p_s)
orders = query(f"""
    SELECT year_month, sum(orders) AS orders FROM olap.mv_delivery_cube {where_d}
    GROUP BY year_month ORDER BY year_month""", p_d)
left, right = st.columns(2)
with left, st.container(border=True):
    charts.show(charts.line(trend, "year_month", "revenue", "Doanh thu theo tháng", "Doanh thu (R$)"),
                "Doanh thu theo tháng")
with right, st.container(border=True):
    charts.show(charts.line(orders, "year_month", "orders", "Số đơn theo tháng", "Số đơn", color=charts.GREEN),
                "Số đơn theo tháng")

st.caption("Các tháng đầu (2016-09 đến 2016-12) và tháng cuối (2018-09) có rất ít đơn do phạm vi dữ liệu nguồn, "
           "nên đường biểu diễn dốc ở hai đầu.")

# --- Cơ cấu
left, right = st.columns(2)
with left, st.container(border=True):
    top_n = st.slider("Số danh mục hiển thị", 5, 20, 10)
    cat = query(f"""
        SELECT category, sum(revenue) AS revenue FROM olap.mv_sales_cube {where_s}
        GROUP BY category ORDER BY revenue DESC LIMIT :n""", {**p_s, "n": top_n})
    charts.show(charts.bar(cat, "category", "revenue", f"Top {top_n} danh mục theo doanh thu", ylabel="Doanh thu (R$)",
                           horizontal=True), f"Top {top_n} danh mục theo doanh thu")
with right, st.container(border=True):
    state = query(f"""
        SELECT customer_state, sum(revenue) AS revenue FROM olap.mv_sales_cube {where_s}
        GROUP BY customer_state ORDER BY revenue DESC LIMIT 15""", p_s)
    charts.show(charts.bar(state, "customer_state", "revenue", "Doanh thu theo bang khách hàng (top 15)",
                           ylabel="Doanh thu (R$)", horizontal=True, height=420), "Doanh thu theo bang khách hàng")

# --- Thanh toán
where_p, p_p = flt.where(prefix="o.")
pay = query(f"""
    SELECT p.payment_type, sum(p.payment_value) AS value, count(*) AS payments,
           avg(p.payment_installments) AS avg_installments
    FROM olap.v_payment p JOIN olap.v_fulfillment o USING (order_id) {where_p}
    GROUP BY p.payment_type ORDER BY value DESC""", p_p)
with st.container(border=True):
    st.subheader("Cơ cấu thanh toán")
    a, b = st.columns(2)
    with a:
        charts.show(charts.bar(pay, "payment_type", "value", "Giá trị thanh toán theo loại", ylabel="R$"),
                    "Giá trị thanh toán theo loại thanh toán")
    b.dataframe(pay.rename(columns={"payment_type": "Loại", "value": "Giá trị", "payments": "Số lần",
                                    "avg_installments": "Số kỳ TB"}), hide_index=True, alt="Cơ cấu thanh toán theo loại")
