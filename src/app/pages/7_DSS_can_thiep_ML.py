"""DSS chọn đơn cần can thiệp: mô hình ML chấm xác suất trễ, rồi xếp hạng đơn theo lợi ích ròng kỳ vọng.

Trang chỉ ghép dữ liệu, nhận giả định của người dùng và hiển thị kết quả. Phần tính toán là code của P3:
load_orders / seller_history (src/ml/late_risk.py), run_kmeans / load_snapshot (src/ml/kmean.py),
score_orders / run_whatif (src/dss/whatif.py). Cách tính: docs/dss_design.md.

Mô hình (phiên bản 2) chỉ dùng được cho ngày quyết định từ mốc available_at trong manifest trở đi.
Nhóm khách là snapshot K-Means tính tại ngày 01 của tháng đang xét (chỉ đơn đã giao trước mốc đó).

Phụ trách: P2 (giao diện), P3 (mô hình và DSS)
"""
import json
from datetime import date
from pathlib import Path

import joblib
import pandas as pd
import streamlit as st

from src.app.components import charts
from src.app.components.data import engine, query
from src.app.components.filters import fmt_pct
from src.app.components.kpi import inject_css, kpi, panel
from src.app.components.labels import vi
from src.common.config import ARTIFACTS_DIR

RUNS_DIR = ARTIFACTS_DIR / "models" / "late_risk"
SEGMENTS_DIR = ARTIFACTS_DIR / "kmeans"
FIRST_YEAR = 2016   # năm có đơn đầu tiên trong kho
# Hệ số mặc định lấy theo ví dụ trong docs/dss_design.md; người dùng sửa được ở thanh bên
DEFAULT_FACTORS = {"Khách mua lại": 1.5, "Khách chi tiêu cao nhất": 1.5, "Khách chi tiêu cao": 1.3,
                   "Khách chi tiêu thấp": 1.0, "Khách lâu chưa mua": 1.0}
# Các mức dùng cho bảng what-if, cộng thêm mức người dùng đang chọn
COST_MULTIPLIERS = (0.5, 1.5, 2)
EFFICACIES = (0.1, 0.25, 0.5, 0.75, 1.0)
PARAMS = {"loss": "Thiệt hại cơ sở", "cost": "Chi phí can thiệp", "efficacy": "Hiệu quả can thiệp"}

st.title("DSS: chọn đơn cần can thiệp")
st.caption("Mô hình ML ước tính xác suất trễ của từng đơn mua trong một ngày. DSS chọn những đơn mà can thiệp sớm "
           "(ưu tiên xử lý, liên hệ người bán, đổi đơn vị vận chuyển...) có lợi ích kỳ vọng lớn hơn chi phí.")
inject_css()

try:
    from src.dss.whatif import REVIEW_QUERY, UNKNOWN, run_whatif, score_orders
    from src.ml.kmean import load_snapshot, run_kmeans
    from src.ml.late_risk import BUNDLE_VERSION, MODEL_NAMES, load_orders, seller_history
except ImportError:
    st.info("Chưa có mô hình và DSS của P3 trong mã nguồn (`src/ml/late_risk.py`, `src/ml/kmean.py`, `src/dss/whatif.py`), "
            "hoặc thiếu thư viện. Cập nhật code mới nhất rồi chạy `pip install -r requirements.txt`.",
            icon=":material/extension:")
    st.stop()


def manifest(run: Path) -> dict:
    try:
        return json.loads((run / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


# Chỉ nhận lần huấn luyện đúng phiên bản hiện tại của P3 (có hiệu chỉnh xác suất và mốc available_at)
runs = sorted((p for p in RUNS_DIR.glob("*") if (p / "seller_history.joblib").exists()
               and manifest(p).get("format_version") == BUNDLE_VERSION), reverse=True)
if not runs:
    st.info("Chưa có mô hình đã huấn luyện theo phiên bản hiện tại. Chạy "
            "`python -m src.ml.late_risk --output-dir artifacts/models/late_risk/temporal_01` "
            "(cần đã chạy ETL) vào một thư mục trống, sau đó tải lại trang.", icon=":material/model_training:")
    st.stop()

with panel("intro"):
    c1, c2, c3 = st.columns([0.85, 1, 1.15])
    c1.markdown(":material/person: **Người ra quyết định**\n\nĐội vận hành, chăm sóc khách hàng.")
    c2.markdown(":material/flag: **Quyết định**\n\nTrong các đơn mua hôm nay, can thiệp vào đơn nào và bao nhiêu đơn.")
    c3.markdown(":material/balance: **Đánh đổi**\n\nCan thiệp tốn chi phí và nhân lực; bỏ qua đơn rủi ro cao thì "
                "đơn dễ trễ, khách đánh giá thấp.")


# --- Hàm tải dữ liệu (có cache)
@st.cache_data(ttl="1h", show_spinner=False)
def day_range() -> tuple[date, date]:
    r = query("SELECT min(order_purchase_timestamp)::date AS lo, max(order_purchase_timestamp)::date AS hi "
              "FROM dw.fact_order_fulfillment").iloc[0]
    return r["lo"], r["hi"]


@st.cache_data(ttl="1h", max_entries=8, show_spinner=False)
def day_orders(day: date) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Đơn mua trong ngày (đủ feature) và liên kết đơn - người bán - tuyến."""
    with engine().connect() as conn:
        return load_orders(conn, decision_day=day)


@st.cache_resource(max_entries=2)
def seller_events(path: str, _mtime: float) -> dict:
    return joblib.load(Path(path) / "seller_history.joblib")


@st.cache_data(max_entries=4, show_spinner=False)
def segments(as_of: date) -> pd.DataFrame:
    """Snapshot K-Means tại as_of: chỉ đơn mua và đã giao trước as_of (có file metadata JSON đi kèm CSV)."""
    path = SEGMENTS_DIR / f"segments_asof_{as_of:%Y%m%d}.csv"
    try:
        return load_snapshot(path)
    except (OSError, ValueError):
        return load_snapshot(run_kmeans(engine(), FIRST_YEAR, as_of.year, output_path=path, as_of=as_of))


def no_segments(day: date) -> pd.DataFrame:
    """Không dùng nhóm khách: bảng rỗng, mọi đơn thuộc nhóm UNKNOWN với hệ số 1."""
    df = pd.DataFrame({"customer_unique_id": pd.Series(dtype="string"), "kmeans_segment": pd.Series(dtype="string")})
    df.attrs["snapshot"] = {"as_of": str(pd.Timestamp(day))}
    return df


@st.cache_data(max_entries=8, show_spinner=False)
def scores(path: str, mtime: float, day: date, seg_as_of: date | None, factors: tuple) -> pd.DataFrame:
    """Xác suất trễ (đã hiệu chỉnh) của mỗi đơn theo từng mô hình, kèm nhóm khách và hệ số thiệt hại."""
    orders, links = day_orders(day)
    history = seller_events(path, mtime)
    pairs = pd.concat([history["links"], links])[["order_id", "seller_id"]].drop_duplicates()
    orders = seller_history(orders, history["train"], pairs)
    segs = segments(seg_as_of) if seg_as_of is not None else no_segments(day)
    return score_orders(path, orders, segs, dict(factors))


@st.cache_data(max_entries=2, show_spinner=False)
def test_split(path: str, mtime: float) -> frozenset:
    return frozenset(json.loads((Path(path) / "manifest.json").read_text())["splits"]["test"])


@st.cache_data(max_entries=2, show_spinner=False)
def model_metrics(path: str, mtime: float) -> pd.DataFrame:
    """Chỉ số đánh giá P3 ghi lại khi huấn luyện (metrics.csv, trên tập kiểm tra theo thời gian)."""
    try:
        return pd.read_csv(Path(path) / "metrics.csv")
    except OSError:
        return pd.DataFrame()


@st.cache_data(ttl="1h", max_entries=8, show_spinner=False)
def actual_late(day: date) -> pd.DataFrame:
    return query("SELECT order_id, is_late FROM dw.fact_order_fulfillment WHERE is_late IS NOT NULL "
                 "AND order_purchase_timestamp >= :d AND order_purchase_timestamp < :d + interval '1 day'", {"d": day})


# --- Đầu vào
try:
    lo, hi = day_range()
except Exception as e:
    st.error(f"Chưa kết nối được kho dữ liệu: {type(e).__name__}", title="Kho dữ liệu chưa sẵn sàng")
    st.stop()

st.sidebar.header("Ngày và mô hình")
run_dir = st.sidebar.selectbox("Lần huấn luyện mô hình", runs, format_func=lambda p: p.name)
info = manifest(run_dir)
ready = date.fromisoformat(str(info["available_at"])[:10])   # mô hình chỉ có sau khi đã thấy hết dữ liệu train + calibration
first_day = max(ready, lo)
if first_day > hi:
    st.warning(f"Mô hình này chỉ dùng được cho đơn mua từ {ready:%d/%m/%Y}, nhưng kho không có đơn sau ngày đó.",
               title="Không có ngày để xét")
    st.stop()
day = st.sidebar.date_input("Ngày mua của các đơn cần xét", value=min(max(date(2018, 5, 1), first_day), hi),
                            min_value=first_day, max_value=hi, format="DD/MM/YYYY", key="dss_day",
                            help=f"Mô hình học từ đơn trước {ready:%d/%m/%Y}, nên chỉ ra quyết định cho đơn mua từ ngày "
                                 "này trở đi (giống dùng mô hình thật: không biết trước tương lai).")
seg_as_of = day.replace(day=1)
use_segments = st.sidebar.toggle("Tính thiệt hại theo nhóm khách (K-Means)", value=True, key="dss_use_segments",
                                 help=f"Phân cụm khách theo RFM trên các đơn đã giao trước {seg_as_of:%d/%m/%Y} "
                                      "(ngày đầu tháng đang xét), để không dùng dữ liệu của tương lai.")

st.sidebar.header("Giả định")
loss = st.sidebar.number_input("Thiệt hại cơ sở khi một đơn bị trễ", min_value=0.0, value=100.0, step=10.0, key="dss_loss",
                               help="Đơn vị tiền tùy chọn, dùng chung với chi phí. Nhân thêm hệ số của nhóm khách.")
cost = st.sidebar.number_input("Chi phí can thiệp một đơn", min_value=0.0, value=5.0, step=1.0, key="dss_cost")
efficacy = st.sidebar.slider("Hiệu quả can thiệp", 0, 100, 50, step=5, format="%d%%", key="dss_efficacy",
                             help="Trong các đơn vốn sẽ trễ, tỷ lệ đơn được can thiệp kịp để giao đúng hạn.") / 100
unlimited = st.sidebar.toggle("Không giới hạn số đơn xử lý", value=False, key="dss_unlimited")
capacity = None if unlimited else int(st.sidebar.number_input(
    "Số đơn xử lý được trong ngày", min_value=0, value=20, step=5, key="dss_capacity"))

factors = {}
if use_segments:
    try:
        with st.spinner(f"Đang phân cụm khách hàng tại {seg_as_of:%d/%m/%Y}..."):
            names = sorted(segments(seg_as_of)["kmeans_segment"].dropna().unique())
    except (ValueError, RuntimeError, OSError) as e:
        st.error(f"Không phân cụm được khách hàng: {e}", title="Lỗi K-Means")
        st.stop()
    edited = st.sidebar.data_editor(
        pd.DataFrame({"segment": names, "factor": [DEFAULT_FACTORS.get(n, 1.0) for n in names]}),
        key=f"factors_{seg_as_of:%Y%m}", hide_index=True, disabled=["segment"], width="stretch",
        column_config={"segment": "Nhóm khách",
                       "factor": st.column_config.NumberColumn("Hệ số thiệt hại", min_value=0.0, step=0.1,
                                                               format="%.1f", required=True)})
    factors = dict(zip(edited["segment"].astype(str), edited["factor"].astype(float)))
    st.sidebar.caption(f"Khách chưa có đơn giao trước {seg_as_of:%d/%m/%Y} thuộc nhóm “{UNKNOWN}”, hệ số 1.")

# --- Tính toán
try:
    with st.spinner("Đang chấm điểm rủi ro trễ bằng 3 mô hình..."):
        mtime = (run_dir / "manifest.json").stat().st_mtime
        sc = scores(str(run_dir), mtime, day, seg_as_of if use_segments else None, tuple(sorted(factors.items())))
        _, links = day_orders(day)
except ValueError as e:
    if "eligible orders" in str(e):
        st.warning(f"Ngày {day:%d/%m/%Y} không có đơn đủ dữ liệu để chấm điểm. Hãy chọn ngày khác.",
                   title="Không có đơn")
    elif "retrain" in str(e):
        st.error("Mô hình đã chọn là bản cũ hoặc chưa sẵn sàng tại ngày đang xét. Huấn luyện lại bằng "
                 "`python -m src.ml.late_risk --output-dir <thư mục trống>`.", title="Cần huấn luyện lại")
    else:
        st.error(f"Không chấm điểm được: {e}")
    st.stop()

costs = [cost] + [round(cost * k, 2) for k in COST_MULTIPLIERS]
efficacies = [efficacy] + list(EFFICACIES)
res = run_whatif(sc, links, loss, costs, efficacies, [capacity])


def base(df: pd.DataFrame) -> pd.DataFrame:
    """Các dòng của kịch bản đang chọn ở thanh bên."""
    return df[df["cost"].eq(cost) & df["efficacy"].eq(efficacy)]


summary = base(res["summary"])
met = model_metrics(str(run_dir), mtime)
# Mặc định: mô hình có average precision cao nhất trên tập kiểm tra (xếp đúng đơn trễ lên đầu là điều DSS cần)
best = met.loc[met["average_precision"].idxmax(), "model"] if not met.empty else "lightgbm"
model = st.segmented_control("Mô hình", list(MODEL_NAMES), default=best, key="dss_model",
                             format_func=lambda m: vi("model", m),
                             help="Mặc định là mô hình xếp hạng đơn trễ tốt nhất trên tập kiểm tra "
                                  "(average precision cao nhất, xem phần đối chiếu cuối trang).") or best
row = summary[summary["model"] == model].iloc[0]
mine = base(res["orders"])
mine = mine[mine["model"] == model].sort_values("rank")
picked = mine[mine["selected"]]

with st.grid(4, gap="small"):
    kpi("Đơn mua trong ngày", f"{len(mine):,}",
        help=f"Đơn đủ dữ liệu để chấm điểm. Mô hình ước tính khoảng {mine['p_late'].sum():,.1f} đơn sẽ trễ.")
    kpi("Đơn nên can thiệp", f"{int(row.selected):,}", "green",
        help="Đơn có lợi ích ròng dương, lấy theo thứ tự lợi ích cho tới khi đủ số đơn xử lý được trong ngày.")
    kpi("Đơn trễ tránh được (kỳ vọng)", f"{row.avoided_late:,.1f}",
        help="Tổng xác suất trễ × hiệu quả can thiệp trên các đơn được chọn.")
    kpi("Lợi ích ròng kỳ vọng", f"{row.net:,.1f}",
        help=f"Lợi ích gộp {row.gross:,.1f} trừ chi phí {row.total_cost:,.1f}, cùng đơn vị tiền với giả định.")

# --- Danh sách gợi ý
st.subheader("Danh sách đơn nên can thiệp")
show_all = st.toggle("Hiện cả đơn không được chọn", value=False, key="dss_show_all")
table = (mine if show_all else picked)[["rank", "order_id", "kmeans_segment", "p_late", "loss_if_late", "gross", "net",
                                        "selected"]]
if table.empty:
    st.info("Với giả định hiện tại, không đơn nào có lợi ích ròng dương. Thử giảm chi phí, tăng hiệu quả "
            "hoặc tăng thiệt hại cơ sở.", icon=":material/info:")
else:
    view = table.rename(columns={"rank": "Thứ tự", "order_id": "Mã đơn", "kmeans_segment": "Nhóm khách",
                                 "p_late": "Xác suất trễ", "loss_if_late": "Thiệt hại nếu trễ",
                                 "gross": "Lợi ích gộp (chưa trừ chi phí)", "net": "Lợi ích ròng", "selected": "Được chọn"})
    st.dataframe(view, hide_index=True, height=min(38 + 35 * len(view), 420),
                 alt=f"Các đơn mua ngày {day:%d/%m/%Y} xếp theo lợi ích ròng kỳ vọng nếu can thiệp",
                 column_config={"Xác suất trễ": st.column_config.ProgressColumn(format="percent", min_value=0, max_value=1),
                                "Thiệt hại nếu trễ": st.column_config.NumberColumn(format="%.1f"),
                                "Lợi ích gộp (chưa trừ chi phí)": st.column_config.NumberColumn(format="%.1f"),
                                "Lợi ích ròng": st.column_config.NumberColumn(format="%+.1f")})
    st.download_button("Tải danh sách (CSV)", view.to_csv(index=False).encode("utf-8-sig"),
                       file_name=f"don_can_thiep_{day:%Y%m%d}_{model}.csv", mime="text/csv",
                       icon=":material/download:")

# --- What-if và độ nhạy
c1, c2 = st.columns(2, gap="medium")
grid = res["summary"][res["summary"]["model"] == model].copy()
grid = grid.sort_values(["cost", "efficacy"], ascending=[False, True])
grid["eff"] = grid["efficacy"].map(lambda v: f"{v:.0%}")
grid["cst"] = grid["cost"].map(lambda v: f"{v:,.1f}")
with c1, st.container(border=True):
    charts.show(charts.heatmap(grid, "eff", "cst", "net", "What-if: lợi ích ròng theo chi phí và hiệu quả",
                               labels=("Hiệu quả can thiệp", "Chi phí một đơn", "Lợi ích ròng"), scheme="greens",
                               axis_titles=True, keep_order=True, height=300),
                "Lợi ích ròng kỳ vọng của ngày đang xét khi đổi chi phí can thiệp và hiệu quả can thiệp")
    st.caption(f"Giữ nguyên thiệt hại cơ sở {loss:,.0f} và số đơn xử lý được "
               f"{'không giới hạn' if capacity is None else capacity}. Mô hình {vi('model', model)}.")

sens = res["sensitivity"]
sens = sens[sens["model"] == model].assign(
    parameter=lambda d: d["parameter"].map(PARAMS),
    change=lambda d: d["change"].map({0.8: "Giảm 20%", 1.2: "Tăng 20%"}),
    delta=lambda d: d["delta_net"])
with c2, st.container(border=True):
    charts.show(charts.tornado(sens, "Độ nhạy: đổi từng giả định ±20%", height=300),
                "Thay đổi lợi ích ròng khi tăng hoặc giảm 20% từng giả định, giữ nguyên các giả định còn lại")
    st.caption("Thanh càng dài thì kết quả càng phụ thuộc vào giả định đó, nên cần ước lượng giả định đó cẩn thận hơn.")

# --- So sánh mô hình và nơi tập trung rủi ro
st.subheader("So sánh 3 mô hình")
st.dataframe(summary.assign(model=summary["model"].map(lambda m: vi("model", m)))[
    ["model", "selected", "total_cost", "avoided_late", "gross", "net"]].rename(columns={
        "model": "Mô hình", "selected": "Đơn được chọn", "total_cost": "Chi phí", "avoided_late": "Đơn trễ tránh được",
        "gross": "Lợi ích gộp (chưa trừ chi phí)", "net": "Lợi ích ròng"}),
    hide_index=True, alt="Kết quả của kịch bản đang chọn theo từng mô hình",
    column_config={c: st.column_config.NumberColumn(format="%.1f")
                   for c in ("Chi phí", "Đơn trễ tránh được", "Lợi ích gộp (chưa trừ chi phí)", "Lợi ích ròng")})

if use_segments:
    st.subheader("Ảnh hưởng của nhóm khách (K-Means)")
    cov = res["segment_coverage"].set_index("model").loc[model]
    abl = base(res["segment_ablation"])
    abl = abl[abl["model"] == model].iloc[0]
    with st.grid(3, gap="small"):
        kpi("Tỷ lệ đơn đã có nhóm khách", fmt_pct(cov.matched_rate),
            help=f"{int(cov.matched):,}/{int(cov.orders):,} đơn của khách đã có trong snapshot K-Means; "
                 f"còn lại thuộc nhóm “{UNKNOWN}”, hệ số 1.")
        kpi("Đơn thay đổi khi dùng nhóm khách", f"{int(abl.changed_orders):,}",
            help=f"Số đơn vào hoặc ra khỏi danh sách so với khi mọi hệ số bằng 1 "
                 f"({int(abl.neutral_selected):,} đơn được chọn nếu bỏ hệ số).")
        kpi("Chênh lệch so với không dùng nhóm khách", f"{abl.delta_net:+,.1f}",
            help="Lợi ích ròng kỳ vọng với hệ số nhóm khách trừ lợi ích khi mọi hệ số bằng 1. Đây là so sánh hai giả định "
                 "thiệt hại, không chứng minh K-Means tạo ra lợi ích thật.")

c1, c2 = st.columns(2, gap="medium")
for col, key, label, title in ((c1, "routes", "route", "Tuyến"), (c2, "sellers", "seller_id", "Người bán")):
    g = base(res[key])
    g = g[g["model"] == model].nlargest(10, "expected_late")
    with col, st.container(border=True):
        charts.show(charts.bar(g, label, "expected_late", f"{title} có nhiều đơn dự kiến trễ nhất",
                               ylabel="Số đơn trễ kỳ vọng", horizontal=True, color=charts.RED, height=300),
                    f"10 {title.lower()} có tổng xác suất trễ cao nhất trong ngày đang xét")

# --- Đối chiếu và giả định
with st.expander("Đối chiếu với kết quả giao thực tế"):
    test_ids = test_split(str(run_dir), mtime)
    check = mine.merge(actual_late(day), on="order_id")
    check = check[check["order_id"].isin(test_ids)]
    if check.empty:
        st.caption("Ngày này chưa có đơn nào thuộc tập kiểm tra đã biết kết quả giao.")
    else:
        sel, rest = check[check["selected"]], check[~check["selected"]]
        st.markdown(
            f"Xét **{len(check)}** đơn trong ngày đã có kết quả giao (đều thuộc tập kiểm tra, mô hình chưa thấy khi huấn luyện).\n\n"
            f"- Đơn được chọn: {len(sel)} đơn, thực tế trễ {fmt_pct(sel['is_late'].astype(float).mean()) if len(sel) else '—'}.\n"
            f"- Đơn không được chọn: {len(rest)} đơn, thực tế trễ "
            f"{fmt_pct(rest['is_late'].astype(float).mean()) if len(rest) else '—'}.\n"
            f"- Mô hình dự kiến {check['p_late'].sum():,.1f} đơn trễ, thực tế {int(check['is_late'].sum())} đơn.\n\n"
            "Nếu nhóm được chọn có tỷ lệ trễ cao hơn hẳn nhóm còn lại thì DSS đang ưu tiên đúng đơn. "
            "Mỗi ngày chỉ có ít đơn nên con số này chỉ để tham khảo.")
    if not met.empty:
        n = int(met["test_n"].iloc[0])
        st.markdown(f"**Chất lượng mô hình trên toàn tập kiểm tra** ({n:,} đơn mua "
                    f"{pd.Timestamp(info['config']['split']['test_start']):%m/%Y}–"
                    f"{pd.Timestamp(info['config']['split']['test_end']) - pd.Timedelta(days=1):%m/%Y}, "
                    f"tỷ lệ trễ thực tế {fmt_pct(met['baseline_ap'].iloc[0])}; số liệu do pipeline của P3 ghi lại):")
        st.dataframe(met.assign(model=met["model"].map(lambda m: vi("model", m)))[
            ["model", "auc", "average_precision", "brier", "threshold", "precision", "recall", "f1"]].rename(columns={
                "model": "Mô hình", "auc": "ROC-AUC", "average_precision": "Average precision", "brier": "Brier",
                "threshold": "Ngưỡng", "precision": "Precision", "recall": "Recall", "f1": "F1"}),
            hide_index=True, alt="Chỉ số đánh giá ba mô hình trên tập kiểm tra theo thời gian",
            column_config={c: st.column_config.NumberColumn(format="%.3f")
                           for c in ("ROC-AUC", "Average precision", "Brier", "Ngưỡng", "Precision", "Recall", "F1")})
        st.caption("ROC-AUC: khả năng xếp đơn trễ cao hơn đơn đúng hạn (0,5 là ngẫu nhiên, 1 là hoàn hảo). "
                   "Average precision: độ chính xác khi xếp đơn trễ lên đầu, so với mức ngẫu nhiên bằng tỷ lệ trễ thực tế. "
                   "Brier: sai số của xác suất, càng nhỏ càng sát thực tế. "
                   "Ngưỡng, Precision, Recall, F1 tính khi coi đơn có xác suất từ ngưỡng trở lên là trễ; "
                   "DSS không dùng ngưỡng này mà dùng trực tiếp xác suất.")

split = info.get("config", {}).get("split", {})
with st.expander("Cách tính và hạn chế"):
    st.markdown(
        "- Thiệt hại khi trễ = thiệt hại cơ sở × hệ số nhóm khách. "
        "Lợi ích ròng = xác suất trễ × thiệt hại khi trễ × hiệu quả − chi phí.\n"
        "- DSS chọn đơn có lợi ích ròng dương, theo thứ tự lợi ích giảm dần, tối đa bằng số đơn xử lý được. "
        "Mỗi mô hình cho một danh sách riêng.\n"
        f"- Mô hình học trên đơn mua từ {pd.Timestamp(split.get('train_start')):%m/%Y} đến trước "
        f"{pd.Timestamp(split.get('train_end')):%d/%m/%Y} (cân bằng 10.000 đơn đúng hạn + 10.000 đơn trễ), rồi hiệu "
        f"chỉnh xác suất (sigmoid) trên đơn mua trước {pd.Timestamp(split.get('calibration_end')):%d/%m/%Y} với tỷ lệ "
        "trễ tự nhiên. Vì vậy xác suất trễ dùng được trực tiếp trong công thức kỳ vọng, và trang chỉ cho chọn ngày sau "
        "mốc này.\n"
        "- Hiệu chỉnh dựa trên giai đoạn trước, nên khi tỷ lệ trễ thay đổi theo mùa, xác suất có thể lệch "
        "(xem phần đối chiếu ở trên).\n"
        "- Nhóm khách là snapshot K-Means tại ngày đầu tháng đang xét, chỉ dùng đơn đã giao trước mốc đó.\n"
        "- Hiệu quả và chi phí can thiệp là giả định của người dùng. Muốn đo hiệu quả thật cần dữ liệu về các lần can thiệp.\n"
        "- Chi tiết: docs/dss_design.md, docs/ml_design.md.")
    try:
        rv = query(REVIEW_QUERY)
    except Exception:
        rv = pd.DataFrame()
    if len(rv) == 2:
        rv = rv.set_index(rv["is_late"].astype(bool))
        lines = [f"- Đơn {name}: trung bình {rv.at[flag, 'mean_stars']:.2f} sao, "
                 f"{fmt_pct(rv.at[flag, 'low_review_rate'])} đánh giá 1–2 sao."
                 for flag, name in ((False, "đúng hạn"), (True, "trễ"))]
        st.markdown("**Căn cứ cho thiệt hại khi trễ** (đơn có đánh giá trong kho):\n\n" + "\n".join(lines))
