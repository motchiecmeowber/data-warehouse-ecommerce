"""Các hàm vẽ biểu đồ phải sinh ra đặc tả Vega-Lite hợp lệ (không cần DB).

Phụ trách: P2
"""
import pandas as pd

from src.app.components import charts


def test_chart_helpers_build_valid_specs():
    df = pd.DataFrame({"m": ["2017-01", "2017-02"], "v": [0.1, 0.2], "g": ["a", "b"], "s": ["SP", "RJ"], "n": [5, 9]})
    specs = [
        charts.line(df, "m", "v", "t", "y", pct=True),
        charts.lines(df, "m", "v", "g", "t", "y", colors={"a": charts.RED, "b": charts.GREEN}),
        charts.bar(df, "s", "v", "t", horizontal=True, pct=True),
        charts.grouped_bar(df, "m", "v", "g", "t", "x", "y", {"a": charts.RED, "b": charts.GREEN}, pct=True),
        charts.heatmap(df, "s", "g", "v", "t", pct=True),
        charts.pareto(df, "v", "n", "t", "x", "y"),
        charts.scatter(df, "v", "n", "n", "g", [charts.alt.Tooltip("s")], "t", "x", "y", "size", "color"),
        charts.tradeoff(pd.DataFrame({"promise_days": [1, 2], "late_rate": [0.5, 0.1], "expected_review": [3.0, 4.0]}), 0.05, 2),
    ]
    for spec in specs:
        assert spec.to_dict()
