"""Giao diện DSS: what-if và gợi ý số ngày hẹn giao theo tuyến và danh mục (tính trong src/olap/dss_baseline.py).

Phụ trách: P2 (giao diện), P3 (mô hình DSS)
"""
import numpy as np
import streamlit as st

from src.app.components import charts
from src.app.components.data import engine, query, require_olap
from src.app.components.filters import fmt_pct
from src.olap import dss_baseline as dss

st.title("DSS: gợi ý ngày hẹn giao")
st.caption("Hỗ trợ chọn số ngày hẹn giao để tỷ lệ giao trễ không vượt mức mong muốn, dựa trên thời gian giao thực tế trong kho dữ liệu.")
require_olap()

with st.container(border=True):
    c1, c2, c3 = st.columns(3)
    c1.markdown("**Người ra quyết định**\n\nQuản lý vận hành, chính sách giao hàng.")
    c2.markdown("**Quyết định**\n\nSố ngày hẹn giao cho từng tuyến và danh mục sản phẩm.")
    c3.markdown("**Đánh đổi**\n\nHẹn ngắn thì hấp dẫn nhưng dễ trễ (review thấp); hẹn dài thì an toàn nhưng kém hấp dẫn.")

# --- Đầu vào
sellers = query("SELECT DISTINCT seller_state FROM olap.v_fulfillment WHERE seller_state IS NOT NULL ORDER BY 1")["seller_state"].tolist()
custs = query("SELECT DISTINCT customer_state FROM olap.v_fulfillment ORDER BY 1")["customer_state"].tolist()
cats = query("SELECT DISTINCT category FROM olap.v_fulfillment WHERE category IS NOT NULL ORDER BY 1")["category"].tolist()
ALL = "(Tất cả)"
st.sidebar.header("Phân khúc")
ss = st.sidebar.selectbox("Bang người bán", [ALL] + sellers, index=([ALL] + sellers).index("SP") if "SP" in sellers else 0)
cs = st.sidebar.selectbox("Bang khách hàng", [ALL] + custs, index=([ALL] + custs).index("RJ") if "RJ" in custs else 0)
cat = st.sidebar.selectbox("Danh mục", [ALL] + cats)
st.sidebar.header("Tham số quyết định")
target = st.sidebar.slider("Mục tiêu tỷ lệ giao trễ tối đa", 0.01, 0.30, 0.05, 0.01, format="%.2f")

seg = dss.load_segment(engine(), None if ss == ALL else ss, None if cs == ALL else cs, None if cat == ALL else cat)
n = len(seg)
st.subheader(f"Phân khúc: {ss} → {cs} · {cat}")
if n < dss.MIN_SEGMENT_ORDERS:
    st.warning(f"Chỉ có {n} đơn đã giao trong phân khúc này (cần ≥ {dss.MIN_SEGMENT_ORDERS}) nên chưa đủ căn cứ để gợi ý. "
               "Hãy mở rộng phân khúc (chọn '(Tất cả)' ở một chiều).", title="Chưa đủ dữ liệu")
    st.stop()

rec = dss.recommend_days(seg, target)
assert rec is not None   # n >= MIN_SEGMENT_ORDERS đã được kiểm tra ở trên
cur_promised = seg["promised_days"].mean()
cur_late = seg["is_late"].astype(bool).mean()
with st.grid(4, gap="small"):
    st.metric("Số đơn đã giao (căn cứ)", f"{n:,}", border=True, height="stretch")
    st.metric("Ngày hẹn hiện tại (TB)", f"{cur_promised:.1f}", border=True, height="stretch")
    st.metric("Tỷ lệ trễ hiện tại", fmt_pct(cur_late), border=True, height="stretch")
    st.metric("Gợi ý ngày hẹn", f"{rec} ngày", delta=f"{rec - cur_promised:+.1f} so với hiện tại", delta_color="off",
              border=True, height="stretch",
              help=f"Số ngày nhỏ nhất để tỷ lệ trễ ≤ {target:.0%} theo phân phối giao hàng thực tế")

# --- What-if
st.subheader("What-if: nếu hẹn P ngày thì sao?")
max_d = int(np.ceil(seg["delivery_days"].quantile(0.99))) + 2
p_ask = st.slider("Ngày hẹn giao thử nghiệm (P)", 1, max_d, int(min(max(rec, 1), max_d)))
curve = dss.late_rate_curve(seg, range(1, max_d + 1))
row = curve[curve["promise_days"] == p_ask].iloc[0]
with st.grid(3, gap="small"):
    st.metric("Tỷ lệ trễ dự kiến", fmt_pct(row.late_rate), delta=f"{(row.late_rate - cur_late) * 100:+.1f} điểm %",
              delta_color="inverse", border=True, height="stretch")
    st.metric("Điểm review kỳ vọng", f"{row.expected_review:.2f}" if row.expected_review == row.expected_review else "–",
              border=True, height="stretch")
    st.metric("Đơn trễ trên 1.000 đơn", f"{row.late_rate * 1000:.0f}", border=True, height="stretch")

with st.container(border=True):
    charts.show(charts.tradeoff(curve, target, p_ask),
                f"Tỷ lệ trễ và điểm review kỳ vọng theo số ngày hẹn; đường cam đánh dấu {p_ask} ngày")

# --- Độ nhạy
st.subheader("Phân tích độ nhạy")
targets = [0.01, 0.02, 0.05, 0.10, 0.15, 0.20]
a, b = st.columns([1, 2])
a.dataframe(dss.sensitivity(seg, targets), hide_index=True, alt="Số ngày hẹn gợi ý theo mục tiêu tỷ lệ trễ")
b.caption("Mục tiêu càng chặt thì ngày hẹn gợi ý càng dài. Dòng nào tăng nhanh bất thường cho thấy phân khúc có "
          "đuôi giao rất chậm (vài đơn trễ nặng) nên khó cam kết chặt.")

# --- Nơi cần xem lại trước
st.subheader("Tuyến cần xem lại ngày hẹn trước")
risky = dss.top_risky_segments(engine())
st.dataframe(risky.rename(columns={"route": "Tuyến", "orders": "Đơn", "avg_promised_days": "Ngày hẹn TB",
                                   "avg_delivery_days": "Ngày giao TB", "p90_delivery_days": "P90 ngày giao",
                                   "late_rate": "Tỷ lệ trễ"}), hide_index=True, alt="Các tuyến có tỷ lệ giao trễ cao nhất",
             column_config={"Tỷ lệ trễ": st.column_config.ProgressColumn(format="percent", min_value=0, max_value=1)})

with st.expander("Giả định và hạn chế"):
    st.markdown(
        "- Phân phối thời gian giao trong quá khứ được giữ nguyên cho tương lai.\n"
        "- Hẹn dài hơn không làm đổi thời gian giao thực tế và **chưa mô hình hóa** việc khách bỏ đơn vì hẹn lâu.\n"
        "- Điểm review kỳ vọng = điểm TB (đúng hạn) × (1 − trễ) + điểm TB (trễ) × trễ, lấy từ review của phân khúc.\n"
        "- Chỉ tính đơn đã giao, đơn hợp lệ; phân khúc dưới 30 đơn không được gợi ý.\n"
        "- Mô hình ML dự đoán rủi ro trễ từng đơn (P3) sẽ bổ sung để gợi ý chính xác hơn cho từng đơn cụ thể."
    )
