"""Trang người bán: doanh thu, tỷ lệ trễ, điểm đánh giá.

Phụ trách: P2
"""
import altair as alt
import streamlit as st

from src.app.components import charts
from src.app.components.data import query, require_olap
from src.app.components.filters import fmt_money, fmt_pct
from src.app.components.kpi import inject_css, kpi
from src.app.components.labels import localize

st.title("Người bán")
require_olap()
inject_css()

st.sidebar.header("Bộ lọc người bán")
states = query("SELECT DISTINCT seller_state FROM olap.mv_seller_scorecard ORDER BY 1")["seller_state"].tolist()
sel_states = st.sidebar.multiselect("Bang người bán", states, placeholder="Tất cả các bang")
min_orders = st.sidebar.slider("Tối thiểu số đơn", 1, 200, 20)
late_thr = st.sidebar.slider("Cảnh báo khi tỷ lệ trễ vượt", 5, 50, 20, 5, format="%d%%") / 100

df = query("SELECT * FROM olap.mv_seller_scorecard")      # cache nguồn, lọc tương tác bên ngoài hàm cache
df = df[df["orders"] >= min_orders]
if sel_states:
    df = df[df["seller_state"].isin(sel_states)]
st.caption("Số liệu tổng hợp toàn thời gian của từng người bán (đơn có nhiều người bán được tính cho từng người bán tham gia).")
if df.empty:
    st.info("Không có người bán nào thỏa bộ lọc.")
    st.stop()

with st.grid(4, gap="small"):
    kpi("Số người bán", f"{len(df):,}")
    kpi("Doanh thu", fmt_money(df["revenue"].sum()))
    kpi("Tỷ lệ trễ chung", fmt_pct(df["late_orders"].sum() / df["delivered_orders"].sum()), "red")
    kpi("Người bán vượt ngưỡng trễ", f"{int((df['late_rate'] > late_thr).sum()):,}", "red")

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
    sc = localize(sc, "seller_region")
    charts.show(charts.scatter(sc, "late_rate", "avg_review_score", "orders", "seller_region",
                               [alt.Tooltip("seller_id", title="Mã người bán"), alt.Tooltip("seller_state", title="Bang"),
                                alt.Tooltip("orders", title="Số đơn"), alt.Tooltip("late_rate", title="Tỷ lệ trễ", format=".1%"),
                                alt.Tooltip("avg_review_score", title="Điểm đánh giá", format=".2f"),
                                alt.Tooltip("revenue", title="Doanh thu (R$)", format=",.0f")],
                               "Tỷ lệ trễ và điểm đánh giá của từng người bán (kích thước = số đơn)", "Tỷ lệ trễ", "Điểm đánh giá trung bình",
                               "Số đơn", "Vùng"), "Tỷ lệ trễ so với điểm đánh giá của từng người bán")

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
      .rename(columns={"seller_id": "Mã người bán", "seller_state": "Bang", "revenue": "Doanh thu (R$)", "orders": "Số đơn",
                       "late_rate": "Tỷ lệ trễ", "avg_delivery_days": "Số ngày giao trung bình",
                       "avg_review_score": "Điểm đánh giá trung bình", "reviews": "Số đánh giá"}),
    hide_index=True, alt="Bảng điểm người bán xếp theo doanh thu",
    column_config={"Tỷ lệ trễ": st.column_config.ProgressColumn(format="percent", min_value=0, max_value=1),
                   "Doanh thu": st.column_config.NumberColumn(format="R$ %.0f")})
