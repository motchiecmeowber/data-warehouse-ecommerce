"""Biểu đồ Altair dùng chung.

Màu mặc định của chuỗi lấy từ theme; chỉ dùng màu cố định cho ý nghĩa ngữ nghĩa (trễ = đỏ, đúng hạn = xanh).
Mỗi biểu đồ khi hiển thị phải qua `show(chart, alt=...)` để có mô tả cho trình đọc màn hình.
"""
import altair as alt
import pandas as pd
import streamlit as st

PRIMARY = "#1D4ED8"   # trùng primaryColor trong .streamlit/config.toml
RED = "#DC2626"
GREEN = "#059669"
GRAY = "#64748B"


def show(chart: alt.Chart | alt.LayerChart, alt_text: str) -> None:
    """Hiển thị biểu đồ; tiêu đề vẽ ngoài biểu đồ vì canvas Vega làm mất dấu ở chữ có hai dấu (ố, ế...)."""
    title = chart.title if isinstance(chart.title, str) else None
    if title:
        chart = chart.copy()
        chart.title = alt.Undefined
        st.markdown(f"#### {title}")
    st.altair_chart(chart, width="stretch", alt=alt_text)


def _axis_format(pct: bool) -> str:
    return ".0%" if pct else "~s"


def line(df: pd.DataFrame, x: str, y: str, title: str, ylabel: str, pct: bool = False,
         color: str | None = None, height: int = 320) -> alt.Chart:
    return alt.Chart(df).mark_line(point=True, color=color or alt.Undefined).encode(
        x=alt.X(f"{x}:O", title=None, axis=alt.Axis(labelAngle=-45)),
        y=alt.Y(f"{y}:Q", title=ylabel, axis=alt.Axis(format=_axis_format(pct))),
        tooltip=[alt.Tooltip(f"{x}:O", title="Tháng"), alt.Tooltip(f"{y}:Q", title=ylabel, format=".1%" if pct else ",.1f")],
    ).properties(title=title, height=height)


def pareto(df: pd.DataFrame, x: str, y: str, title: str, xlabel: str, ylabel: str, height: int = 320) -> alt.Chart:
    """Đường cong lũy kế: cả hai trục là tỷ trọng (0-100%)."""
    return alt.Chart(df).mark_line(color=PRIMARY).encode(
        x=alt.X(f"{x}:Q", title=xlabel, axis=alt.Axis(format=".0%")),
        y=alt.Y(f"{y}:Q", title=ylabel, axis=alt.Axis(format=".0%")),
        tooltip=[alt.Tooltip(f"{x}:Q", title=xlabel, format=".1%"), alt.Tooltip(f"{y}:Q", title=ylabel, format=".1%")],
    ).properties(title=title, height=height)


def lines(df: pd.DataFrame, x: str, y: str, series: str, title: str, ylabel: str,
          colors: dict[str, str] | None = None, height: int = 320) -> alt.Chart:
    """Nhiều đường (df ở dạng dài: cột x, y, series)."""
    color = alt.Color(f"{series}:N", title=None, legend=alt.Legend(orient="bottom"),
                      scale=alt.Scale(domain=list(colors), range=list(colors.values())) if colors else alt.Undefined)
    return alt.Chart(df).mark_line(point=True).encode(
        x=alt.X(f"{x}:O", title=None, axis=alt.Axis(labelAngle=-45)),
        y=alt.Y(f"{y}:Q", title=ylabel),
        color=color,
        tooltip=[alt.Tooltip(f"{x}:O", title="Tháng"), alt.Tooltip(f"{series}:N", title="Loại"),
                 alt.Tooltip(f"{y}:Q", title=ylabel, format=",.1f")],
    ).properties(title=title, height=height)


def bar(df: pd.DataFrame, x: str, y: str, title: str, xlabel: str = "", ylabel: str = "", horizontal: bool = False,
        pct: bool = False, color: str | None = None, height: int = 360) -> alt.Chart:
    """Cột / thanh. Thứ tự hiển thị giữ nguyên thứ tự dòng trong df (sort=None)."""
    base = alt.Chart(df).mark_bar(color=color or alt.Undefined)
    cat = alt.X(f"{x}:N", title=xlabel or None, sort=None, axis=alt.Axis(labelAngle=-45))
    val = alt.Y(f"{y}:Q", title=ylabel or None, axis=alt.Axis(format=_axis_format(pct)))
    if horizontal:
        cat = alt.Y(f"{x}:N", title=xlabel or None, sort=None)
        val = alt.X(f"{y}:Q", title=ylabel or None, axis=alt.Axis(format=_axis_format(pct)))
        enc = dict(y=cat, x=val)
    else:
        enc = dict(x=cat, y=val)
    return base.encode(**enc, tooltip=[alt.Tooltip(f"{x}:N", title=xlabel or x),
                                        alt.Tooltip(f"{y}:Q", title=ylabel or y, format=".1%" if pct else ",.1f")]
                       ).properties(title=title, height=height)


def grouped_bar(df: pd.DataFrame, x: str, y: str, group: str, title: str, xlabel: str, ylabel: str,
                colors: dict[str, str], pct: bool = False, height: int = 340) -> alt.Chart:
    return alt.Chart(df).mark_bar().encode(
        x=alt.X(f"{x}:O", title=xlabel), xOffset=alt.XOffset(f"{group}:N"),
        y=alt.Y(f"{y}:Q", title=ylabel, axis=alt.Axis(format=_axis_format(pct))),
        color=alt.Color(f"{group}:N", title=None, legend=alt.Legend(orient="bottom"),
                        scale=alt.Scale(domain=list(colors), range=list(colors.values()))),
        tooltip=[alt.Tooltip(f"{x}:O", title=xlabel), alt.Tooltip(f"{group}:N", title="Nhóm"),
                 alt.Tooltip(f"{y}:Q", title=ylabel, format=".1%" if pct else ",.1f")],
    ).properties(title=title, height=height)


def heatmap(df: pd.DataFrame, x: str, y: str, z: str, title: str, pct: bool = False, height: int = 420) -> alt.LayerChart:
    base = alt.Chart(df).encode(x=alt.X(f"{x}:N", title=None), y=alt.Y(f"{y}:N", title=None))
    fmt = ".0%" if pct else ".1f"
    cells = base.mark_rect().encode(
        color=alt.Color(f"{z}:Q", title=None, scale=alt.Scale(scheme="oranges"), legend=alt.Legend(format=fmt, orient="bottom")),
        tooltip=[alt.Tooltip(f"{y}:N", title="Bang người bán"), alt.Tooltip(f"{x}:N", title="Bang khách"),
                 alt.Tooltip(f"{z}:Q", title="Tỷ lệ trễ", format=".1%" if pct else ".1f")])
    labels = base.mark_text(fontSize=11).encode(
        text=alt.Text(f"{z}:Q", format=fmt),
        color=alt.condition(alt.datum[z] > df[z].quantile(0.7), alt.value("white"), alt.value("black")))
    return (cells + labels).properties(title=title, height=height)


def scatter(df: pd.DataFrame, x: str, y: str, size: str, color: str, tooltip: list[alt.Tooltip], title: str,
            xlabel: str, ylabel: str, size_label: str, color_label: str, height: int = 380) -> alt.Chart:
    return alt.Chart(df).mark_circle(opacity=0.6).encode(
        x=alt.X(f"{x}:Q", title=xlabel, axis=alt.Axis(format=".0%")),
        y=alt.Y(f"{y}:Q", title=ylabel, scale=alt.Scale(zero=False)),
        size=alt.Size(f"{size}:Q", title=size_label, legend=None),
        color=alt.Color(f"{color}:N", title=color_label, legend=alt.Legend(orient="bottom")),
        tooltip=tooltip,
    ).properties(title=title, height=height)


def tradeoff(curve: pd.DataFrame, target: float, promise_days: int, height: int = 380) -> alt.LayerChart:
    """DSS: tỷ lệ trễ (trục trái, đỏ) và điểm đánh giá kỳ vọng (trục phải, xanh) theo số ngày hẹn."""
    base = alt.Chart(curve).encode(x=alt.X("promise_days:Q", title="Số ngày hẹn"))
    late = base.mark_line(color=RED).encode(
        y=alt.Y("late_rate:Q", title="Tỷ lệ trễ", axis=alt.Axis(format=".0%", titleColor=RED)),
        tooltip=[alt.Tooltip("promise_days:Q", title="Ngày hẹn"), alt.Tooltip("late_rate:Q", title="Tỷ lệ trễ", format=".1%")])
    review = base.mark_line(color=PRIMARY).encode(
        y=alt.Y("expected_review:Q", title="Điểm đánh giá kỳ vọng", scale=alt.Scale(zero=False),
                axis=alt.Axis(titleColor=PRIMARY)),
        tooltip=[alt.Tooltip("promise_days:Q", title="Ngày hẹn"), alt.Tooltip("expected_review:Q", title="Điểm đánh giá", format=".2f")])
    goal = alt.Chart(pd.DataFrame({"y": [target]})).mark_rule(strokeDash=[4, 4], color=GRAY).encode(y=alt.Y("y:Q", axis=None))
    pick = alt.Chart(pd.DataFrame({"x": [promise_days]})).mark_rule(strokeDash=[6, 3], color="#EA580C").encode(x="x:Q")
    return alt.layer(alt.layer(late, goal), review, pick).resolve_scale(y="independent").properties(
        title="Đánh đổi giữa ngày hẹn, tỷ lệ trễ và điểm đánh giá", height=height)
