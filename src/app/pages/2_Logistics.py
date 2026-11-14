"""Trang logistics: thời gian giao, tỷ lệ trễ theo tuyến/bang.

Phụ trách: P2
"""
import streamlit as st

from src.app.components import charts
from src.app.components.data import query, require_olap
from src.app.components.filters import fmt_pct, sidebar_filters
from src.app.components.kpi import inject_css, kpi

st.title("Logistics: thời gian giao và giao trễ")
st.caption("Thời gian giao và tỷ lệ giao trễ theo tháng, bang khách, tuyến người bán → khách và từng chặng vận chuyển.")
require_olap()
inject_css()
flt = sidebar_filters()
where, p = flt.where()
# Chỉ tính đơn đã giao (có ngày khách nhận)
w_del = (where + " AND " if where else "WHERE ") + "delivered_orders > 0"

k = query(f"""
    SELECT sum(delivered_orders) AS delivered, sum(late_orders) AS late,
           sum(sum_delivery_days) / nullif(sum(n_delivery_days), 0) AS avg_days,
           sum(sum_promised_days) / nullif(sum(n_promised_days), 0) AS avg_promised
    FROM olap.mv_delivery_cube {w_del}""", p).iloc[0]


def days(v) -> str:
    return f"{v:.1f} ngày" if v is not None and v == v else "–"


with st.grid(4, gap="small"):
    kpi("Đơn đã giao", f"{int(k.delivered or 0):,}")
    kpi("Tỷ lệ giao trễ", fmt_pct(k.late / k.delivered if k.delivered else None), "red")
    kpi("Thời gian giao trung bình", days(k.avg_days))
    kpi("Ngày hẹn trung bình", days(k.avg_promised))

# on_change="rerun": chỉ tab đang mở mới chạy truy vấn
tab_trend, tab_geo, tab_route, tab_stage = st.tabs(
    ["Xu hướng", "Theo bang", "Theo tuyến", "Các chặng và đánh giá"], key="logistics_tabs", on_change="rerun")

if tab_trend.open:
    with tab_trend:
        t = query(f"""
            SELECT year_month, sum(late_orders)::float / nullif(sum(delivered_orders), 0) AS late_rate,
                   sum(sum_delivery_days) / nullif(sum(n_delivery_days), 0) AS avg_days,
                   sum(sum_promised_days) / nullif(sum(n_promised_days), 0) AS avg_promised
            FROM olap.mv_delivery_cube {w_del} GROUP BY year_month
            HAVING sum(delivered_orders) >= 30 ORDER BY year_month""", p)
        st.caption("Chỉ vẽ các tháng có từ 30 đơn đã giao trở lên (tháng ít đơn cho tỷ lệ thất thường, ví dụ 1 đơn trễ = 100%).")
        a, b = st.columns(2)
        with a, st.container(border=True):
            charts.show(charts.line(t, "year_month", "late_rate", "Tỷ lệ giao trễ theo tháng", "Tỷ lệ trễ",
                                    color=charts.RED, pct=True), "Tỷ lệ giao trễ theo tháng")
        m = t.melt("year_month", ["avg_days", "avg_promised"], var_name="loai", value_name="ngay")
        m["loai"] = m["loai"].map({"avg_days": "Giao thực tế", "avg_promised": "Ngày hẹn"})
        with b, st.container(border=True):
            charts.show(charts.lines(m, "year_month", "ngay", "loai", "Thời gian giao thực tế so với ngày hẹn (ngày)", "Ngày",
                                     colors={"Giao thực tế": charts.PRIMARY, "Ngày hẹn": charts.GRAY}),
                        "Thời gian giao thực tế so với ngày hẹn theo tháng")

if tab_geo.open:
    with tab_geo:
        g = query(f"""
            SELECT customer_state, sum(delivered_orders) AS delivered,
                   sum(late_orders)::float / nullif(sum(delivered_orders), 0) AS late_rate,
                   sum(sum_delivery_days) / nullif(sum(n_delivery_days), 0) AS avg_days
            FROM olap.mv_delivery_cube {w_del} GROUP BY customer_state
            HAVING sum(delivered_orders) >= 20 ORDER BY late_rate DESC""", p)
        a, b = st.columns(2)
        with a, st.container(border=True):
            charts.show(charts.bar(g, "customer_state", "late_rate", "Tỷ lệ giao trễ theo bang khách (bang ≥ 20 đơn)",
                                   ylabel="Tỷ lệ trễ", color=charts.RED, pct=True, horizontal=True, height=620),
                        "Tỷ lệ giao trễ theo bang khách")
        with b, st.container(border=True):
            charts.show(charts.bar(g.sort_values("avg_days", ascending=False), "customer_state", "avg_days",
                                   "Thời gian giao TB theo bang khách (ngày)", ylabel="Ngày", horizontal=True, height=620),
                        "Thời gian giao trung bình theo bang khách")

if tab_route.open:
    with tab_route:
        min_orders = st.slider("Số đơn đã giao tối thiểu của mỗi tuyến", 10, 300, 50, step=10)
        r = query(f"""
            SELECT seller_state, customer_state, sum(delivered_orders) AS delivered,
                   sum(late_orders)::float / nullif(sum(delivered_orders), 0) AS late_rate,
                   sum(sum_delivery_days) / nullif(sum(n_delivery_days), 0) AS avg_days
            FROM olap.mv_delivery_cube {w_del} AND seller_state IS NOT NULL
            GROUP BY seller_state, customer_state HAVING sum(delivered_orders) >= :mo""", {**p, "mo": min_orders})
        if r.empty:
            st.info("Không có tuyến nào đủ số đơn với bộ lọc hiện tại.")
        else:
            top_sellers = r.groupby("seller_state")["delivered"].sum().nlargest(8).index
            top_cust = r.groupby("customer_state")["delivered"].sum().nlargest(10).index
            h = r[r["seller_state"].isin(top_sellers) & r["customer_state"].isin(top_cust)]
            with st.container(border=True):
                charts.show(charts.heatmap(h, "customer_state", "seller_state", "late_rate",
                                           "Tỷ lệ trễ: bang người bán (hàng) → bang khách (cột)", pct=True),
                            "Bản đồ nhiệt tỷ lệ giao trễ theo tuyến bang người bán đến bang khách")
            r["route"] = r["seller_state"] + " → " + r["customer_state"]
            st.dataframe(r.sort_values("late_rate", ascending=False)[["route", "delivered", "late_rate", "avg_days"]]
                         .rename(columns={"route": "Tuyến", "delivered": "Đơn đã giao", "late_rate": "Tỷ lệ trễ",
                                          "avg_days": "Số ngày giao trung bình"}),
                         hide_index=True, alt="Bảng tuyến giao hàng xếp theo tỷ lệ trễ",
                         column_config={"Tỷ lệ trễ": st.column_config.ProgressColumn(format="percent", min_value=0, max_value=1),
                                        "Số ngày giao trung bình": st.column_config.NumberColumn(format="%.1f")})
            st.caption("Tuyến = bang người bán của dòng hàng có doanh thu lớn nhất trong đơn (1,3% đơn có nhiều người bán).")

if tab_stage.open:
    with tab_stage:
        w_o, p_o = flt.where()
        w_j, p_j = flt.where(prefix="o.")
        stage = query(f"""
            SELECT avg(approval_days) AS "Duyệt đơn", avg(handling_days) AS "Người bán chuẩn bị",
                   avg(transit_days) AS "Vận chuyển"
            FROM olap.v_fulfillment {w_o + (' AND ' if w_o else 'WHERE ')} is_delivered""", p_o).iloc[0]
        a, b = st.columns(2)
        sd = stage.rename_axis("Chặng").reset_index(name="Số ngày trung bình")
        with a, st.container(border=True):
            charts.show(charts.bar(sd, "Chặng", "Số ngày trung bình", "Thời gian trung bình của từng chặng (ngày)"),
                        "Thời gian trung bình của từng chặng giao hàng")
        rv = query(f"""
            SELECT CASE WHEN o.is_late THEN 'Giao trễ' ELSE 'Đúng hạn / sớm' END AS delivery, r.review_score, count(*) AS n
            FROM olap.v_review r JOIN olap.v_fulfillment o USING (order_id)
            {w_j + (' AND ' if w_j else 'WHERE ')} o.is_delivered
            GROUP BY 1, 2""", p_j)
        if not rv.empty:
            rv["share"] = rv["n"] / rv.groupby("delivery")["n"].transform("sum")
            with b, st.container(border=True):
                charts.show(charts.grouped_bar(rv, "review_score", "share", "delivery", "Phân bố điểm đánh giá: giao trễ so với đúng hạn",
                                               "Điểm đánh giá", "Tỷ trọng đơn", {"Giao trễ": charts.RED, "Đúng hạn / sớm": charts.GREEN},
                                               pct=True), "Phân bố điểm đánh giá khi giao trễ và khi đúng hạn")
                avg = rv.assign(w=rv["review_score"] * rv["n"]).groupby("delivery")[["w", "n"]].sum()
                st.caption("Điểm TB: " + " · ".join(f"{i}: {r.w / r.n:.2f}" for i, r in avg.iterrows()))
