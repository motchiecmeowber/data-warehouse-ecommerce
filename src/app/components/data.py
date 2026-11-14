"""Truy cập dữ liệu cho dashboard: engine dùng chung + cache kết quả truy vấn."""
import pandas as pd
import streamlit as st

from src.common.db import get_engine
from src.olap.cube import run_query


@st.cache_resource
def engine():
    return get_engine()


# Mỗi bộ lọc tạo một mục cache nên giới hạn số mục
@st.cache_data(ttl="10m", max_entries=256, show_spinner=False)
def query(sql: str, params: dict | None = None) -> pd.DataFrame:
    return run_query(engine(), sql, params)


def require_olap() -> None:
    """Dừng trang với thông báo rõ ràng nếu kho / view olap chưa sẵn sàng."""
    try:
        n = query("SELECT count(*) AS n FROM olap.mv_sales_cube").iloc[0, 0]
    except Exception as e:
        st.error("Chưa kết nối được kho dữ liệu hoặc chưa tạo view OLAP.", title="Kho dữ liệu chưa sẵn sàng")
        st.code("docker compose up -d\npython -m src.sql.init_db\npython -m src.etl.run_etl\n"
                "python -m src.olap.build", language="bash")
        st.caption(f"Chi tiết lỗi: {type(e).__name__}: {str(e).splitlines()[0][:300]}")
        st.stop()
    if n == 0:
        st.warning("Chạy ETL rồi `python -m src.olap.build --refresh`.", title="View OLAP đang rỗng")
        st.stop()
