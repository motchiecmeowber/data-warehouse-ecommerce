"""Trang người bán: doanh thu, tỷ lệ trễ, điểm review.

Phụ trách: P2
"""
import streamlit as st

from src.app.components import charts
from src.app.components.data import query, require_olap
from src.app.components.filters import fmt_money, fmt_pct

st.title("Người bán")
require_olap()

st.sidebar.header("Bộ lọc người bán")
states = query("SELECT DISTINCT seller_state FROM olap.mv_seller_scorecard ORDER BY 1")["seller_state"].tolist()
sel_states = st.sidebar.multiselect("Bang người bán", states)
min_orders = st.sidebar.slider("Tối thiểu số đơn", 1, 200, 20)
late_thr = st.sidebar.slider("Ngưỡng tỷ lệ trễ cần cảnh báo", 0.05, 0.5, 0.2, 0.05, format="%.2f")

df = query("SELECT * FROM olap.mv_seller_scorecard")      # cache nguồn, lọc tương tác bên ngoài hàm cache
df = df[df["orders"] >= min_orders]
if sel_states:
    df = df[df["seller_state"].isin(sel_states)]
st.caption("Số liệu tổng hợp toàn thời gian của từng người bán (đơn nhiều người bán được tính cho mỗi người bán tham gia).")
if df.empty:
    st.info("Không có người bán nào thỏa bộ lọc.")
    st.stop()

with st.container(horizontal=True):
    st.metric("Số người bán", f"{len(df):,}", border=True)
    st.metric("Doanh thu", fmt_money(df["revenue"].sum()), border=True)
    st.metric("Tỷ lệ trễ (gộp)", fmt_pct(df["late_orders"].sum() / df["delivered_orders"].sum()), border=True)
    st.metric("Người bán trễ > ngưỡng", f"{int((df['late_rate'] > late_thr).sum()):,}", border=True)

a, b = st.columns(2)
top = df.nlargest(10, "revenue")
top = top.assign(label=top["seller_id"].str[:8] + " (" + top["seller_state"] + ")")
with a, st.container(border=True):
    charts.show(charts.bar(top, "label", "revenue", "Top 10 người bán theo doanh thu", ylabel="R$", horizontal=True),
                "Top 10 người bán theo doanh thu")
with b, st.container(border=True):
    sc = df.dropna(subset=["late_rate", "avg_review_score"]).copy()
    sc["late_rate"] = sc["late_rate"].astype(float)
    sc["avg_review_score"] = sc["avg_review_score"].astype(float)
    charts.show(charts.scatter(sc, "late_rate", "avg_review_score", "orders", "seller_region",
                               ["seller_id", "seller_state", "orders", "late_rate", "avg_review_score", "revenue"],
                               "Tỷ lệ trễ và điểm review (kích thước = số đơn)", "Tỷ lệ trễ", "Điểm review TB",
                               "Số đơn", "Vùng"), "Tỷ lệ trễ so với điểm review của từng người bán")

# Mức tập trung doanh thu (Pareto)
s = df.sort_values("revenue", ascending=False).reset_index(drop=True)
s["share_sellers"] = (s.index + 1) / len(s)
s["share_revenue"] = s["revenue"].cumsum() / s["revenue"].sum()
a, b = st.columns(2)
with a, st.container(border=True):
    charts.show(charts.pareto(s, "share_sellers", "share_revenue", "Mức tập trung doanh thu (Pareto)",
                              "Tỷ trọng người bán (xếp theo doanh thu)", "Tỷ trọng doanh thu lũy kế"),
                "Đường cong mức tập trung doanh thu của người bán")
    n20 = max(1, round(len(s) * 0.2))
    st.caption(f"20% người bán hàng đầu ({n20:,}) chiếm {fmt_pct(s['share_revenue'].iloc[n20 - 1])} doanh thu.")
by_state = df.groupby("seller_state").agg(sellers=("seller_id", "count"), revenue=("revenue", "sum")).reset_index()
with b, st.container(border=True):
    charts.show(charts.bar(by_state.sort_values("revenue", ascending=False).head(12), "seller_state", "revenue",
                           "Doanh thu theo bang người bán (top 12)", ylabel="R$"), "Doanh thu theo bang người bán")

st.subheader("Bảng điểm người bán")
st.dataframe(
    df.sort_values("revenue", ascending=False)[["seller_id", "seller_state", "revenue", "orders", "late_rate",
                                                "avg_delivery_days", "avg_review_score", "reviews"]]
      .rename(columns={"seller_id": "Mã người bán", "seller_state": "Bang", "revenue": "Doanh thu", "orders": "Số đơn",
                       "late_rate": "Tỷ lệ trễ", "avg_delivery_days": "Ngày giao TB",
                       "avg_review_score": "Điểm review", "reviews": "Số review"}),
    hide_index=True, alt="Bảng điểm người bán xếp theo doanh thu",
    column_config={"Tỷ lệ trễ": st.column_config.ProgressColumn(format="percent", min_value=0, max_value=1),
                   "Doanh thu": st.column_config.NumberColumn(format="R$ %.0f")})
