"""Giao diện DSS: what-if và gợi ý số ngày hẹn giao theo tuyến và danh mục (tính trong src/olap/dss_baseline.py).

Phụ trách: P2 (giao diện), P3 (mô hình DSS)
"""
import numpy as np
import streamlit as st

from src.app.components import charts
from src.app.components.data import engine, query, require_olap
from src.app.components.filters import fmt_pct
from src.app.components.kpi import inject_css, kpi, panel
from src.app.components.labels import vi
from src.olap import dss_baseline as dss

st.title("DSS: gợi ý ngày hẹn giao")
st.caption("Gợi ý số ngày hẹn giao để tỷ lệ giao trễ không vượt mức chấp nhận, dựa trên thời gian giao thực tế trong kho dữ liệu.")
require_olap()
inject_css()

with panel("intro"):
    c1, c2, c3 = st.columns([0.85, 1, 1.15])
    c1.markdown(":material/person: **Người ra quyết định**\n\nQuản lý vận hành, chính sách giao hàng.")
    c2.markdown(":material/flag: **Quyết định**\n\nSố ngày hẹn giao cho từng tuyến và danh mục sản phẩm.")
    c3.markdown(":material/balance: **Đánh đổi**\n\nHẹn ngắn thì hấp dẫn nhưng dễ trễ (đánh giá thấp); hẹn dài thì an toàn nhưng kém hấp dẫn.")

# --- Đầu vào
sellers = query("SELECT DISTINCT seller_state FROM olap.v_fulfillment WHERE seller_state IS NOT NULL ORDER BY 1")["seller_state"].tolist()
custs = query("SELECT DISTINCT customer_state FROM olap.v_fulfillment ORDER BY 1")["customer_state"].tolist()
cats = query("SELECT DISTINCT category FROM olap.v_fulfillment WHERE category IS NOT NULL ORDER BY 1")["category"].tolist()
ALL = "(Tất cả)"
st.sidebar.header("Nhóm đơn hàng")
ss = st.sidebar.selectbox("Bang người bán", [ALL] + sellers, index=([ALL] + sellers).index("SP") if "SP" in sellers else 0)
cs = st.sidebar.selectbox("Bang khách hàng", [ALL] + custs, index=([ALL] + custs).index("RJ") if "RJ" in custs else 0)
cat = st.sidebar.selectbox("Danh mục sản phẩm", [ALL] + cats, format_func=lambda c: c if c == ALL else vi("category", c))
st.sidebar.header("Tham số quyết định")
target = st.sidebar.slider("Tỷ lệ giao trễ tối đa chấp nhận", 1, 30, 5, format="%d%%") / 100

seg = dss.load_segment(engine(), None if ss == ALL else ss, None if cs == ALL else cs, None if cat == ALL else cat)
n = len(seg)
st.subheader(f"Nhóm đang xét: {ss} → {cs} · {'Mọi danh mục' if cat == ALL else vi('category', cat)}")
if n < dss.MIN_SEGMENT_ORDERS:
    st.warning(f"Nhóm này chỉ có {n} đơn đã giao (cần ít nhất {dss.MIN_SEGMENT_ORDERS}) nên chưa đủ căn cứ để gợi ý. "
               "Hãy mở rộng nhóm bằng cách chọn '(Tất cả)' ở một mục.", title="Chưa đủ dữ liệu")
    st.stop()

rec = dss.recommend_days(seg, target)
assert rec is not None   # n >= MIN_SEGMENT_ORDERS đã được kiểm tra ở trên
cur_promised = seg["promised_days"].mean()
cur_late = seg["is_late"].astype(bool).mean()
with st.grid(4, gap="small"):
    kpi("Số đơn đã giao dùng để tính", f"{n:,}")
    kpi("Ngày hẹn hiện tại (trung bình)", f"{cur_promised:.1f}")
    kpi("Tỷ lệ trễ hiện tại", fmt_pct(cur_late), "red")
    kpi("Gợi ý ngày hẹn", f"{rec} ngày", "green", delta=f"{rec - cur_promised:+.1f} so với hiện tại",
        delta_color="off", help=f"Số ngày nhỏ nhất để tỷ lệ trễ ≤ {target:.0%} theo phân phối giao hàng thực tế")

# --- What-if
st.subheader("What-if: nếu hẹn P ngày thì sao?")
max_d = int(np.ceil(seg["delivery_days"].quantile(0.99))) + 2
p_ask = st.slider("Ngày hẹn giao thử nghiệm (P)", 1, max_d, int(min(max(rec, 1), max_d)))
curve = dss.late_rate_curve(seg, range(1, max_d + 1))
row = curve[curve["promise_days"] == p_ask].iloc[0]
with st.grid(3, gap="small"):
    kpi("Tỷ lệ trễ dự kiến", fmt_pct(row.late_rate), "red",
        delta=f"{(row.late_rate - cur_late) * 100:+.1f} điểm %", delta_color="inverse")
    kpi("Điểm đánh giá kỳ vọng", f"{row.expected_review:.2f}" if row.expected_review == row.expected_review else "–")
    kpi("Số đơn trễ trên 1.000 đơn", f"{row.late_rate * 1000:.0f}")

with st.container(border=True):
    charts.show(charts.tradeoff(curve, target, p_ask),
                f"Tỷ lệ trễ và điểm đánh giá kỳ vọng theo số ngày hẹn; đường cam đánh dấu {p_ask} ngày")

# --- Độ nhạy
st.subheader("Phân tích độ nhạy")
targets = [0.01, 0.02, 0.05, 0.10, 0.15, 0.20]
a, b = st.columns([1, 2])
a.dataframe(dss.sensitivity(seg, targets), hide_index=True, alt="Số ngày hẹn gợi ý theo mục tiêu tỷ lệ trễ")
b.caption("Mục tiêu càng chặt thì ngày hẹn gợi ý càng dài. Nếu số ngày tăng vọt ở mục tiêu rất thấp, "
          "nhóm này có một số đơn giao rất chậm nên khó cam kết chặt.")

# --- Nơi cần xem lại trước
st.subheader("Tuyến cần xem lại ngày hẹn trước")
risky = dss.top_risky_segments(engine())
st.dataframe(risky.rename(columns={"route": "Tuyến (bang người bán → bang khách)", "orders": "Số đơn",
                                   "avg_promised_days": "Ngày hẹn trung bình", "avg_delivery_days": "Ngày giao trung bình",
                                   "p90_delivery_days": "Ngày giao của 90% đơn nhanh hơn", "late_rate": "Tỷ lệ trễ"}), hide_index=True, alt="Các tuyến có tỷ lệ giao trễ cao nhất",
             column_config={"Tỷ lệ trễ": st.column_config.ProgressColumn(format="percent", min_value=0, max_value=1)})

with st.expander("Giả định và hạn chế"):
    st.markdown(
        "- Phân phối thời gian giao trong quá khứ được giữ nguyên cho tương lai.\n"
        "- Hẹn dài hơn không làm đổi thời gian giao thực tế và **chưa mô hình hóa** việc khách bỏ đơn vì hẹn lâu.\n"
        "- Điểm đánh giá kỳ vọng = điểm trung bình khi đúng hạn × (1 − tỷ lệ trễ) + điểm trung bình khi trễ × tỷ lệ trễ, lấy từ đánh giá của nhóm.\n"
        "- Chỉ tính đơn đã giao, đơn hợp lệ; nhóm dưới 30 đơn không được gợi ý.\n"
        "- Mô hình ML dự đoán rủi ro trễ từng đơn (P3) sẽ bổ sung để gợi ý chính xác hơn cho từng đơn cụ thể."
    )
