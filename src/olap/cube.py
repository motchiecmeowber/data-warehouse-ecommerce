"""Truy vấn OLAP có tham số trên các materialized view, dùng cho dashboard.

Tên cột lấy từ danh sách cố định (DIMENSIONS, MEASURES), giá trị người dùng chọn đi qua tham số ràng buộc.

Phụ trách: P2
"""
from dataclasses import dataclass, field

import pandas as pd
from sqlalchemy import text

# Chiều của mv_sales_cube. Phân cấp: Thời gian (năm > quý > tháng), Địa lý khách (vùng > bang)
DIMENSIONS: dict[str, str] = {
    "year": "Năm",
    "quarter": "Quý",
    "year_month": "Tháng",
    "category": "Danh mục sản phẩm",
    "customer_region": "Vùng (khách hàng)",
    "customer_state": "Bang (khách hàng)",
    "seller_state": "Bang (người bán)",
    "order_status": "Trạng thái đơn",
}
HIERARCHIES: dict[str, list[str]] = {
    "Thời gian": ["year", "quarter", "year_month"],
    "Địa lý khách hàng": ["customer_region", "customer_state"],
}
MEASURES: dict[str, tuple[str, str]] = {
    "revenue": ("sum(revenue)", "Doanh thu"),
    "freight": ("sum(freight)", "Phí vận chuyển"),
    "units": ("sum(units)", "Số sản phẩm bán"),
    "line_items": ("sum(line_items)", "Số dòng hàng"),
}


@dataclass
class Filters:
    """Bộ lọc chung của dashboard. Rỗng / None = không lọc."""
    month_from: str | None = None          # 'YYYY-MM'
    month_to: str | None = None
    regions: list[str] = field(default_factory=list)
    states: list[str] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)
    valid_only: bool = True                # chỉ đơn không hủy / không có hàng

    def where(self, *, categories: bool = False, prefix: str = "") -> tuple[str, dict]:
        """Sinh mệnh đề WHERE + tham số. categories=True chỉ khi bảng có cột category."""
        conds, params = [], {}
        if self.month_from:
            conds.append(f"{prefix}year_month >= :month_from"); params["month_from"] = self.month_from
        if self.month_to:
            conds.append(f"{prefix}year_month <= :month_to"); params["month_to"] = self.month_to
        if self.regions:
            conds.append(f"{prefix}customer_region = ANY(:regions)"); params["regions"] = list(self.regions)
        if self.states:
            conds.append(f"{prefix}customer_state = ANY(:states)"); params["states"] = list(self.states)
        if categories and self.categories:
            conds.append(f"{prefix}category = ANY(:categories)"); params["categories"] = list(self.categories)
        if self.valid_only:
            conds.append(f"{prefix}is_valid_sale")
        return ("WHERE " + " AND ".join(conds)) if conds else "", params


def run_query(engine, sql: str, params: dict | None = None) -> pd.DataFrame:
    with engine.connect() as conn:
        return pd.read_sql(text(sql), conn, params=params or {})


def aggregate(engine, rows: list[str], cols: list[str], measure: str, flt: Filters,
              rollup: bool = False) -> tuple[pd.DataFrame, str]:
    """Tổng hợp mv_sales_cube theo các chiều `rows` (+ `cols` nếu pivot). Trả về (DataFrame, câu SQL).

    rollup=True: thêm các dòng tổng cấp trên (GROUP BY ROLLUP) theo thứ tự `rows`.
    """
    dims = rows + [c for c in cols if c not in rows]
    for d in dims:
        if d not in DIMENSIONS:
            raise ValueError(f"Chiều không hợp lệ: {d}")
    if measure not in MEASURES:
        raise ValueError(f"Số đo không hợp lệ: {measure}")
    where, params = flt.where(categories=True)
    expr = MEASURES[measure][0]
    if not dims:
        sql = f"SELECT {expr} AS value\nFROM olap.mv_sales_cube\n{where}"
    else:
        select = ", ".join(dims)
        group = f"ROLLUP ({select})" if rollup else select
        sql = (f"SELECT {select}, {expr} AS value\nFROM olap.mv_sales_cube\n{where}\n"
               f"GROUP BY {group}\nORDER BY {select}")
    df = run_query(engine, sql, params)
    for d in ("year", "quarter"):          # NaN ở dòng tổng làm cột số thành float (2017.0) -> ép về số nguyên có null
        if d in df.columns:
            df[d] = df[d].astype("Int64")
    return df, sql
