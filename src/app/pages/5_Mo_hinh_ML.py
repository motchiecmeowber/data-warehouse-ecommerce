"""Phân cụm khách hàng trên toàn bộ đơn hợp lệ trong khoảng năm đã chọn (K-Means theo RFM, code src/ml/kmean.py).

Phụ trách: P2 (giao diện), P3 (mô hình)
"""

import pandas as pd
import streamlit as st
from sqlalchemy.exc import SQLAlchemyError

from src.app.components.filters import fmt_money, fmt_pct
from src.app.components.kpi import inject_css, kpi, panel
from src.common.db import get_engine
from src.ml.kmean import run_kmeans

# Thứ tự hiển thị các nhóm (tên nhóm do kmean.py gán theo trung vị RFM của từng cụm)
ORDER = ["Khách mua lại", "Khách chi tiêu cao nhất", "Khách chi tiêu cao", "Khách chi tiêu thấp", "Khách lâu chưa mua"]
COLUMNS = {"customer_unique_id": "Mã khách", "kmeans_segment": "Nhóm khách", "recency_days": "Số ngày từ lần mua cuối",
           "frequency": "Số đơn", "monetary": "Tổng chi tiêu (R$)", "avg_order_value": "Giá trị đơn TB (R$)"}

st.title("Phân cụm khách hàng")
st.caption("K-Means chia khách thành 4 nhóm theo RFM: mua gần đây đến mức nào (Recency), mua bao nhiêu đơn (Frequency) "
           "và chi bao nhiêu tiền (Monetary). Lọc theo ngày mua, bao gồm cả năm kết thúc.")
inject_css()

with panel("intro"):
    c1, c2, c3 = st.columns([0.85, 1, 1.15])
    c1.markdown(":material/person: **Người dùng**\n\nĐội marketing, chăm sóc khách hàng.")
    c2.markdown(":material/flag: **Mục đích**\n\nBiết khách thuộc nhóm nào để ưu tiên giữ chân và chăm sóc phù hợp.")
    c3.markdown(":material/link: **Dùng ở đâu**\n\nTrang *DSS chọn đơn can thiệp (ML)* nhân thiệt hại khi trễ theo nhóm khách.")

# --- Đầu vào: chỉ chạy khi bấm nút vì K-Means trên toàn bộ khách mất vài giây
# Không dùng st.form: dòng gợi ý "Press Enter to submit form" bị đè lên ô số trong thanh bên hẹp
st.sidebar.header("Khoảng dữ liệu")
start_year = st.sidebar.number_input("Từ năm", min_value=1, max_value=9998, value=2017, step=1)
end_year = st.sidebar.number_input("Đến năm", min_value=1, max_value=9998, value=2018, step=1)
submitted = st.sidebar.button("Phân cụm khách hàng", icon=":material/groups:", type="primary", width="stretch")

if submitted:
    st.session_state.pop("customer_segments", None)
    if start_year > end_year:
        st.error("Năm bắt đầu phải nhỏ hơn hoặc bằng năm kết thúc.", title="Khoảng năm không hợp lệ")
    else:
        try:
            engine = get_engine()
            try:
                with st.spinner("Đang đọc dữ liệu và phân cụm..."):
                    path = run_kmeans(engine, start_year, end_year)
                    result = pd.read_csv(path, dtype={"customer_unique_id": "string"})
            finally:
                engine.dispose()
        except (ValueError, RuntimeError, SQLAlchemyError, OSError):
            st.error("Kiểm tra kết nối database, dữ liệu và ít nhất 4 hồ sơ RFM khác nhau trong khoảng năm đã chọn.",
                     title="Không thể phân cụm")
        else:
            st.session_state["customer_segments"] = (start_year, end_year, result)

if "customer_segments" not in st.session_state:
    st.info("Chọn khoảng năm ở thanh bên rồi bấm **Phân cụm khách hàng**.", icon=":material/info:")
    st.stop()

from src.app.components import charts  # nạp muộn: Altair nặng, lần mở trang đầu chưa cần

trained_start, trained_end, result = st.session_state["customer_segments"]
st.subheader(f"Kết quả {trained_start}–{trained_end}")
has_rfm = {"recency_days", "frequency", "monetary"}.issubset(result.columns)

with st.grid(4, gap="small"):
    kpi("Số khách hàng", f"{len(result):,}")
    kpi("Số nhóm", f"{result['kmeans_segment'].nunique():,}")
    if has_rfm:
        kpi("Khách mua từ 2 đơn", fmt_pct((result["frequency"] > 1).mean()),
            help="Tỷ lệ khách có nhiều hơn một đơn trong khoảng năm đã chọn.")
        kpi("Chi tiêu trung bình", fmt_money(result["monetary"].mean()),
            help="Tổng tiền hàng trung bình của một khách, không gồm phí vận chuyển.")

order = [s for s in ORDER if s in set(result["kmeans_segment"])] + sorted(set(result["kmeans_segment"]) - set(ORDER))
counts = (result["kmeans_segment"].value_counts().reindex(order).rename_axis("segment").reset_index(name="customers"))
counts["share"] = counts["customers"] / counts["customers"].sum()

c1, c2 = st.columns(2, gap="medium")
with c1, st.container(border=True):
    charts.show(charts.bar(counts, "segment", "customers", "Số khách theo nhóm", ylabel="Số khách", horizontal=True,
                           height=300),
                "Số khách hàng trong từng nhóm K-Means")
with c2, st.container(border=True):
    st.markdown("#### Chân dung từng nhóm")
    if has_rfm:
        profile = result.groupby("kmeans_segment")[["recency_days", "frequency", "monetary", "avg_order_value"]].median()
        profile = counts.set_index("segment").join(profile).reset_index()
        st.dataframe(profile.rename(columns={"segment": "Nhóm khách", "customers": "Số khách", "share": "Tỷ trọng",
                                             "recency_days": "Ngày từ lần mua cuối", "frequency": "Số đơn",
                                             "monetary": "Tổng chi tiêu (R$)", "avg_order_value": "Giá trị đơn TB (R$)"}),
                     hide_index=True, alt="Số khách, tỷ trọng và trung vị RFM của từng nhóm khách",
                     column_config={"Tỷ trọng": st.column_config.NumberColumn(format="percent"),
                                    "Số khách": st.column_config.NumberColumn(format="localized"),
                                    "Ngày từ lần mua cuối": st.column_config.NumberColumn(format="%.0f"),
                                    "Số đơn": st.column_config.NumberColumn(format="%.0f"),
                                    "Tổng chi tiêu (R$)": st.column_config.NumberColumn(format="%.2f"),
                                    "Giá trị đơn TB (R$)": st.column_config.NumberColumn(format="%.2f")})
        st.caption("Các chỉ số RFM là trung vị trong nhóm. Tên nhóm được gán theo trung vị RFM của từng cụm "
                   "(xem docs/ml_design.md), nên là nhãn tương đối trong khoảng năm đã chọn.")
    else:
        st.dataframe(counts.rename(columns={"segment": "Nhóm khách", "customers": "Số khách", "share": "Tỷ trọng"}),
                     hide_index=True, column_config={"Tỷ trọng": st.column_config.NumberColumn(format="percent")})

st.subheader("Danh sách khách hàng")
view = result[[c for c in COLUMNS if c in result.columns]].rename(columns=COLUMNS)
st.dataframe(view, hide_index=True, alt="Nhóm K-Means và chỉ số RFM của từng khách hàng",
             column_config={"Tổng chi tiêu (R$)": st.column_config.NumberColumn(format="%.2f"),
                            "Giá trị đơn TB (R$)": st.column_config.NumberColumn(format="%.2f")})
st.download_button("Tải danh sách (CSV)", view.to_csv(index=False).encode("utf-8-sig"),
                   file_name=f"phan_cum_khach_{trained_start}_{trained_end}.csv", mime="text/csv",
                   icon=":material/download:")
st.caption("Đây là phân cụm để khám phá trên toàn bộ khoảng năm. Trang DSS chọn đơn can thiệp tự tính lại nhóm khách "
           "chỉ với dữ liệu trước ngày quyết định, để không dùng thông tin của tương lai.")
