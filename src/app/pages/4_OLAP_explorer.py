"""Chọn chiều để roll-up / drill-down / slice / dice.

Phụ trách: P2
"""
import streamlit as st

from src.app.components.data import engine, require_olap
from src.app.components.filters import sidebar_filters
from src.olap import console
from src.olap.cube import DIMENSIONS, HIERARCHIES, MEASURES, aggregate

st.title("OLAP explorer")
require_olap()

# on_change="rerun": chỉ tab đang mở mới chạy truy vấn
tab_cube, tab_sql = st.tabs(["Khối dữ liệu (cube)", "Truy vấn SQL"], key="olap_tabs", on_change="rerun")

if tab_cube.open:
    with tab_cube:
        flt = sidebar_filters(with_category=True, key="olap")
        st.caption("Slice / dice: dùng bộ lọc ở thanh bên (chọn 1 giá trị = slice, nhiều giá trị = dice). "
                   "Roll-up / drill-down: chọn cấp của phân cấp bên dưới.")

        c1, c2 = st.columns([1, 2])
        measure = c1.selectbox("Số đo", list(MEASURES), format_func=lambda m: MEASURES[m][1])
        op = c2.segmented_control("Cách xem", ["Thời gian", "Địa lý khách hàng", "Tự chọn chiều"],
                                  default="Thời gian", key="olap_view") or "Thời gian"
        rows: list[str] = []
        if op in HIERARCHIES:
            levels = HIERARCHIES[op]
            # Mỗi mức là đường đi từ cấp cao nhất: "Năm", "Năm › Quý", "Năm › Quý › Tháng"
            paths = [" › ".join(DIMENSIONS[lv] for lv in levels[:i]) for i in range(1, len(levels) + 1)]
            chosen = st.segmented_control("Mức chi tiết", paths, default=paths[0], key="olap_depth",
                                          help="Chọn mức sâu hơn để drill-down (chi tiết hơn), mức nông hơn để roll-up (gộp lại).")
            depth = paths.index(chosen) + 1 if chosen in paths else 1
            st.caption(f"Đang xem theo **{paths[depth - 1]}**. "
                       + ("Chọn mức sâu hơn để drill-down." if depth < len(levels) else "Đây là mức chi tiết nhất; chọn mức nông hơn để roll-up."))
            rows = levels[:depth]
            extra = st.multiselect("Thêm chiều vào hàng", [d for d in DIMENSIONS if d not in rows],
                                   format_func=lambda d: DIMENSIONS[d], placeholder="Không bắt buộc")
            rows += extra
        else:
            rows = st.multiselect("Chiều ở hàng", list(DIMENSIONS), default=["category"], format_func=lambda d: DIMENSIONS[d],
                                  placeholder="Chọn ít nhất một chiều")
        cols = st.multiselect("Chiều ở cột (pivot)", [d for d in DIMENSIONS if d not in rows], max_selections=1,
                              format_func=lambda d: DIMENSIONS[d], placeholder="Không pivot")
        rollup = st.checkbox("Thêm dòng tổng từng cấp (ROLLUP)", value=False, disabled=bool(cols) or len(rows) < 2,
                             help="Chỉ dùng khi có từ 2 chiều ở hàng và không pivot")

        if not rows:
            st.info("Chọn ít nhất một chiều ở hàng.")
        else:
            df, sql = aggregate(engine(), rows, cols, measure, flt, rollup=rollup and not cols)
            if cols:
                df = df.pivot_table(index=rows, columns=cols[0], values="value", aggfunc="sum").reset_index()
                df.columns = [str(c) for c in df.columns]
            st.write(f"**{len(df):,} dòng**")
            shown = df.copy()
            for d in rows:      # chiều hiển thị dạng chữ (canh trái); ô trống ở dòng tổng ghi là "Tổng"
                shown[d] = shown[d].astype("string").fillna("Tổng")
            shown = shown.rename(columns={**DIMENSIONS, "value": MEASURES[measure][1]})
            numeric = {c: st.column_config.NumberColumn(format="localized") for c in shown.columns
                       if c not in [DIMENSIONS[r] for r in rows]}
            st.dataframe(shown, hide_index=True, column_config=numeric,
                         alt=f"Kết quả OLAP: {MEASURES[measure][1]} theo " + ", ".join(DIMENSIONS[r] for r in rows))
            st.download_button("Tải CSV", df.to_csv(index=False).encode("utf-8-sig"), "olap_result.csv", "text/csv",
                               icon=":material/download:")
            if not cols and len(rows) <= 2 and not rollup:
                st.bar_chart(shown, x=DIMENSIONS[rows[0]], y=MEASURES[measure][1],
                             color=DIMENSIONS[rows[1]] if len(rows) == 2 else None,
                             alt=f"{MEASURES[measure][1]} theo {DIMENSIONS[rows[0]]}")
            with st.expander("Câu SQL đã sinh"):
                st.code(sql, language="sql")
            st.caption("Số đơn không có trong khối này vì đếm đơn không cộng dồn được khi gộp theo danh mục; "
                       "xem truy vấn `COUNT(DISTINCT order_id)` ở tab SQL.")

if tab_sql.open:
    with tab_sql:
        st.caption("Chỉ đọc: một câu SELECT / WITH trên schema `olap` (v_sales, v_fulfillment, v_payment, v_review, mv_*). "
                   f"Tối đa {console.MAX_ROWS:,} dòng, quá {console.TIMEOUT_MS // 1000}s sẽ bị dừng.")
        examples = console.load_example_queries()
        pick = st.selectbox("Truy vấn mẫu (src/olap/queries)", ["(tự viết)"] + list(examples))
        default = examples.get(pick, "SELECT year_month, sum(item_revenue) AS revenue\nFROM olap.v_sales\n"
                                     "WHERE is_valid_sale\nGROUP BY year_month\nORDER BY year_month")
        sql_text = st.text_area("SQL", default, height=220, key=f"sql_{pick}")
        if st.button("Chạy", type="primary", icon=":material/play_arrow:"):
            try:
                res = console.run_readonly(engine(), sql_text)
            except ValueError as e:
                st.error(str(e))
            except Exception as e:
                st.error(f"Lỗi khi chạy truy vấn: {str(e).splitlines()[0]}")
            else:
                st.write(f"**{len(res):,} dòng**" + (" (đã cắt bớt)" if len(res) >= console.MAX_ROWS else ""))
                st.dataframe(res, hide_index=True, alt="Kết quả truy vấn SQL")
                st.download_button("Tải CSV", res.to_csv(index=False).encode("utf-8-sig"), "query_result.csv", "text/csv",
                                   key="dl_sql", icon=":material/download:")
