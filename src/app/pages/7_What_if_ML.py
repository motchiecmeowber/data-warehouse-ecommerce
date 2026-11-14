"""What-if theo mô hình ML: dời ngày hẹn giao của các đơn rồi xem rủi ro trễ thay đổi ra sao.

Gọi run_whatif / summarize (src/dss/whatif.py) và model train bởi src/ml/late_risk.py (P3).

Phụ trách: P2 (giao diện), P3 (mô hình)
"""
import pandas as pd
import streamlit as st

from src.app.components import charts
from src.app.components.filters import fmt_pct
from src.app.components.kpi import inject_css, kpi
from src.app.components.labels import vi
from src.common.config import ARTIFACTS_DIR

RUNS_DIR = ARTIFACTS_DIR / "models" / "late_risk"
SHIFTS = range(-3, 11)

st.title("What-if: rủi ro giao trễ theo mô hình ML")
st.caption("Dời ngày hẹn giao của từng đơn thêm hoặc bớt vài ngày, rồi để 3 mô hình dự đoán lại đơn nào có nguy cơ trễ.")
inject_css()

try:
    from src.dss.whatif import build_scenario, load_models, run_whatif, summarize  # ty: ignore[import-not-found]
    from src.ml.late_risk import MODEL_NAMES, predict_late  # ty: ignore[import-not-found]
except ImportError:
    st.info("Chưa có mô hình giao trễ của P3 trong mã nguồn (`src/ml/late_risk.py`, `src/dss/whatif.py`), "
            "hoặc thiếu thư viện. Cập nhật code mới nhất rồi chạy `pip install -r requirements.txt`.",
            icon=":material/extension:")
    st.stop()

runs = sorted((p for p in RUNS_DIR.glob("*") if (p / "manifest.json").exists()), reverse=True)
if not runs:
    st.info("Chưa có model. Chạy `python -m src.ml.late_risk --output-dir artifacts/models/late_risk/run_01` "
            "(cần đã chạy ETL), sau đó tải lại trang.", icon=":material/model_training:")
    st.stop()


@st.cache_resource(max_entries=2)
def cached_models(path: str, _mtime: float):
    return load_models(path)


@st.cache_data(max_entries=16)
def whatif(path: str, mtime: float, orders: pd.DataFrame, days: int) -> pd.DataFrame:
    return run_whatif(path, orders, days)


@st.cache_data(max_entries=16)
def shift_curve(path: str, mtime: float, orders: pd.DataFrame) -> pd.DataFrame:
    """Số đơn bị cảnh báo trễ và rủi ro trung bình của từng model ứng với mỗi mức dời ngày hẹn."""
    models = cached_models(path, mtime)
    rows = []
    for days in SHIFTS:
        scenario = build_scenario(orders, days)
        for name, bundle in models.items():
            pred = predict_late(bundle, scenario)
            rows.append({"model": vi("model", name), "days": days, "alerts": int(pred.predicted_label.sum()),
                         "risk": float(pred.risk_score.mean())})
    return pd.DataFrame(rows)


# --- Đầu vào
c1, c2 = st.columns([1, 1.4])
run_dir = c1.selectbox("Lần train", runs, format_func=lambda p: p.name)
source = c2.segmented_control("Đơn hàng cần xét", ["example", "upload"], default="example", key="whatif_source",
                              format_func=lambda s: "Đơn mẫu của lần train" if s == "example" else "Tải file CSV")
if source == "upload":
    file = st.file_uploader("File CSV đơn hàng (cùng cột với example_orders.csv)", type="csv")
    if file is None:
        st.caption("Mỗi dòng một đơn: mã đơn, thời điểm đặt, ngày hẹn, khoảng cách, phí vận chuyển, danh mục, "
                   "lịch sử trễ của người bán... Xem danh sách cột trong docs/dss_design.md.")
        st.stop()
    orders = pd.read_csv(file, dtype={"order_id": "string"})
else:
    orders = pd.read_csv(run_dir / "example_orders.csv", dtype={"order_id": "string"})

mtime = (run_dir / "manifest.json").stat().st_mtime
days = st.slider("Dời ngày hẹn giao (ngày, số âm = hẹn sớm hơn)", SHIFTS.start, SHIFTS.stop - 1, 3)

try:
    with st.spinner("Đang chấm rủi ro..."):
        results = whatif(str(run_dir), mtime, orders, days)
        curve = shift_curve(str(run_dir), mtime, orders)
except ValueError as e:
    st.error(f"Dữ liệu đơn hàng không hợp lệ: {e}")
    st.stop()

summary = summarize(results)
default_model = "lightgbm" if "lightgbm" in MODEL_NAMES else MODEL_NAMES[0]
model = st.segmented_control("Mô hình", list(MODEL_NAMES), default=default_model, key="whatif_model",
                             format_func=lambda m: vi("model", m)) or default_model
row = summary[summary["model"] == model].iloc[0]
mine = results[results["model"] == model]
before, after = mine[mine.scenario == "before"], mine[mine.scenario == "after"]

# --- Kết quả của model đang chọn
with st.grid(4, gap="small"):
    kpi("Số đơn", f"{row.orders:,}")
    kpi("Đơn bị cảnh báo trễ", f"{row.alerts_after}", "red",
        delta=f"{row.alerts_after - row.alerts_before:+d} so với hiện tại", delta_color="inverse")
    kpi("Rủi ro trễ trung bình", fmt_pct(after.risk_score.mean()),
        delta=f"{(after.risk_score.mean() - before.risk_score.mean()) * 100:+.1f} điểm %", delta_color="inverse")
    kpi("Đơn chuyển từ trễ sang đúng hạn", f"{row.late_to_on_time}", "green",
        help=f"Ngược lại, có {row.on_time_to_late} đơn chuyển từ đúng hạn sang trễ")

with st.container(border=True):
    charts.show(charts.lines(curve, "days", "alerts", "model", "Số đơn bị cảnh báo trễ theo số ngày dời hẹn",
                             "Số đơn bị cảnh báo", xlabel="Số ngày dời", height=300),
                "Số đơn bị mô hình cảnh báo trễ khi dời ngày hẹn từ -3 đến 10 ngày, theo từng mô hình")

st.subheader("Chi tiết từng đơn")
detail = before[["order_id", "estimated_delivery_date", "risk_score", "label"]].merge(
    after[["order_id", "estimated_delivery_date", "risk_score", "risk_delta", "label"]],
    on="order_id", suffixes=("_before", "_after"))
labels = {"On time": "Đúng hạn", "Late": "Trễ"}
detail["label_before"] = detail["label_before"].map(labels)
detail["label_after"] = detail["label_after"].map(labels)
pct = st.column_config.ProgressColumn(format="percent", min_value=0, max_value=1)
st.dataframe(detail.rename(columns={
    "order_id": "Mã đơn", "estimated_delivery_date_before": "Ngày hẹn hiện tại", "risk_score_before": "Rủi ro hiện tại",
    "label_before": "Dự đoán hiện tại", "estimated_delivery_date_after": "Ngày hẹn mới", "risk_score_after": "Rủi ro mới",
    "risk_delta": "Thay đổi", "label_after": "Dự đoán mới"}), hide_index=True,
    alt="Rủi ro trễ của từng đơn trước và sau khi dời ngày hẹn",
    column_config={"Rủi ro hiện tại": pct, "Rủi ro mới": pct,
                   "Thay đổi": st.column_config.NumberColumn(format="%+.3f"),
                   "Ngày hẹn hiện tại": st.column_config.DateColumn(format="DD/MM/YYYY"),
                   "Ngày hẹn mới": st.column_config.DateColumn(format="DD/MM/YYYY")})

st.subheader("Tổng hợp cả 3 mô hình")
st.dataframe(summary.assign(model=summary["model"].map(lambda m: vi("model", m))).rename(columns={
    "model": "Mô hình", "estimated_days": "Số ngày dời", "orders": "Số đơn", "alerts_before": "Cảnh báo hiện tại",
    "alerts_after": "Cảnh báo sau khi dời", "on_time_to_late": "Đúng hạn → trễ", "late_to_on_time": "Trễ → đúng hạn"}),
    hide_index=True, alt="Số đơn bị cảnh báo trễ trước và sau khi dời ngày hẹn, theo từng mô hình")

with st.expander("Cách tính và hạn chế"):
    threshold = before["threshold"].iloc[0]
    st.markdown(
        f"- Đơn bị cảnh báo trễ khi rủi ro mô hình dự đoán ≥ ngưỡng {threshold:.2f}.\n"
        "- Chỉ đổi ngày hẹn (và số ngày hẹn tính từ lúc đặt); khoảng cách, phí vận chuyển, lịch sử người bán giữ nguyên.\n"
        "- Dời ngày hẹn không làm hàng giao nhanh hơn: kết quả cho biết cam kết mới có dễ bị trễ hay không, "
        "không chứng minh quan hệ nhân quả.\n"
        "- Rủi ro là điểm của mô hình, chưa hiệu chỉnh thành xác suất thật; các mô hình train trên dữ liệu cân bằng 50:50 "
        "nên rủi ro thường cao hơn tỷ lệ trễ thực tế.\n"
        "- Chi tiết cách train và chọn mô hình: docs/dss_design.md."
    )
