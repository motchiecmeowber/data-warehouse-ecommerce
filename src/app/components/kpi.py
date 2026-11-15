"""Thẻ KPI và khung thông tin: thẻ phẳng, viền mảnh, bo góc.

Thẻ mặc định trung tính. Chỉ chỉ số giao trễ (đỏ) và kết quả gợi ý (xanh lá) được nhấn màu.
"""
import zlib

import streamlit as st

ACCENTS = {"red": (229, 72, 77), "green": (18, 165, 122)}

_BASE = (
    'div[class*="st-key-kpi-"] { background: rgba(100,116,139,0.06); border: 1px solid rgba(100,116,139,0.25); '
    'border-radius: 12px; padding: 0.9rem 1.1rem; box-shadow: 0 1px 2px rgba(15,23,42,0.04); }\n'
)

# Đường kẻ dọc giữa các cột trong panel
_DIVIDER = (
    'div[class*="st-key-kpi-neutral-"] [data-testid="stColumn"] + [data-testid="stColumn"] '
    '{ border-left: 1px solid rgba(100,116,139,0.30); padding-left: 1.5rem; }\n'
)


def inject_css() -> None:
    """Gọi một lần ở đầu trang có dùng kpi() hoặc panel()."""
    accents = "".join(
        f'div[class*="st-key-kpi-{tone}-"] {{ background: rgba({r},{g},{b},0.06); border-color: rgba({r},{g},{b},0.40); }}\n'
        f'div[class*="st-key-kpi-{tone}-"] [data-testid="stMetricValue"] {{ color: rgb({r},{g},{b}); }}\n'
        for tone, (r, g, b) in ACCENTS.items()
    )
    st.html(f"<style>{_BASE}{accents}{_DIVIDER}</style>")


def kpi(label: str, value: str, tone: str = "neutral", **metric_kwargs) -> None:
    """Một thẻ KPI, giãn đủ ô khi đặt trong st.grid. tone: 'neutral', 'red' hoặc 'green'."""
    key = f"kpi-{tone}-{zlib.crc32(label.encode()):08x}"
    with st.container(key=key, width="stretch", height="stretch"):
        st.metric(label, value, **metric_kwargs)


def panel(name: str):
    """Khung thông tin cùng kiểu với thẻ KPI; dùng như `with panel("intro"):`."""
    return st.container(key=f"kpi-neutral-{name}")
