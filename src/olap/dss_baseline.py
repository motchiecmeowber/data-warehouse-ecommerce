"""Gợi ý số ngày hẹn giao từ phân phối thời gian giao thực tế trong kho (không dùng ML).

Với mỗi phân khúc (tuyến, danh mục), tỷ lệ trễ khi hẹn P ngày là tỷ lệ đơn đã giao có delivery_days > P.
Số ngày gợi ý là P nhỏ nhất để tỷ lệ trễ không vượt mục tiêu. Điểm review kỳ vọng tính từ điểm trung bình
khi đúng hạn và khi trễ của phân khúc.

Phụ trách: P2
"""
import numpy as np
import pandas as pd

from src.olap.cube import run_query

MIN_SEGMENT_ORDERS = 30


def load_segment(engine, seller_state: str | None, customer_state: str | None,
                 category: str | None, month_from: str | None = None, month_to: str | None = None) -> pd.DataFrame:
    """Đơn đã giao của một phân khúc (None = tất cả), kèm điểm review (nếu có)."""
    conds = ["o.is_delivered", "o.delivery_days IS NOT NULL", "o.is_valid_sale"]
    params: dict = {}
    for col, val, name in [("seller_state", seller_state, "ss"), ("customer_state", customer_state, "cs"),
                           ("category", category, "cat"), ("year_month", month_from, "mf"),
                           ("year_month", month_to, "mt")]:
        if val:
            op = ">=" if name == "mf" else "<=" if name == "mt" else "="
            conds.append(f"o.{col} {op} :{name}")
            params[name] = val
    sql = f"""
        SELECT o.delivery_days, o.promised_days, o.is_late, r.review_score
        FROM olap.v_fulfillment o
        LEFT JOIN (SELECT order_id, avg(review_score) AS review_score FROM olap.v_review GROUP BY order_id) r
               ON r.order_id = o.order_id
        WHERE {' AND '.join(conds)}"""
    return run_query(engine, sql, params)


def late_rate_curve(df: pd.DataFrame, days_range: range) -> pd.DataFrame:
    """Bảng what-if: với mỗi số ngày hẹn P -> tỷ lệ trễ và điểm review kỳ vọng."""
    d = df["delivery_days"].to_numpy(dtype=float)
    score = df["review_score"]
    late_flag_hist = df["is_late"].astype(bool)
    on_time = score[~late_flag_hist].mean()
    late = score[late_flag_hist].mean()
    rows = []
    for p in days_range:
        late_rate = float((d > p).mean())
        exp_score = (on_time * (1 - late_rate) + late * late_rate) if pd.notna(on_time) and pd.notna(late) else np.nan
        rows.append({"promise_days": p, "late_rate": late_rate, "expected_review": exp_score})
    return pd.DataFrame(rows)


def recommend_days(df: pd.DataFrame, target_late_rate: float) -> int | None:
    """Số ngày hẹn nhỏ nhất (làm tròn lên) để tỷ lệ trễ thực nghiệm <= mục tiêu."""
    if len(df) < MIN_SEGMENT_ORDERS:
        return None
    d = np.sort(df["delivery_days"].to_numpy(dtype=float))
    candidates = np.arange(0, int(np.ceil(d[-1])) + 1)
    late = 1 - np.searchsorted(d, candidates, side="right") / len(d)
    return int(candidates[np.argmax(late <= target_late_rate + 1e-12)])


def sensitivity(df: pd.DataFrame, targets: list[float]) -> pd.DataFrame:
    """Độ nhạy của gợi ý theo mục tiêu tỷ lệ trễ."""
    return pd.DataFrame({
        "Mục tiêu tỷ lệ trễ": [f"{t:.0%}" for t in targets],
        "Số ngày hẹn gợi ý": [recommend_days(df, t) for t in targets],
    })


def top_risky_segments(engine, min_orders: int = 50, limit: int = 15) -> pd.DataFrame:
    """Các tuyến có tỷ lệ trễ cao nhất."""
    sql = """
        SELECT route, count(*) AS orders,
               round(avg(promised_days)::numeric, 1)           AS avg_promised_days,
               round(avg(delivery_days)::numeric, 1)           AS avg_delivery_days,
               round(percentile_cont(0.9) WITHIN GROUP (ORDER BY delivery_days)::numeric, 1) AS p90_delivery_days,
               round(avg(is_late::int)::numeric, 4)            AS late_rate
        FROM olap.v_fulfillment
        WHERE is_delivered AND is_valid_sale AND route IS NOT NULL AND delivery_days IS NOT NULL
        GROUP BY route HAVING count(*) >= :min_orders
        ORDER BY late_rate DESC LIMIT :limit"""
    return run_query(engine, sql, {"min_orders": min_orders, "limit": limit})
