"""Kiểm thử các trang dashboard bằng AppTest của Streamlit.

Cần DB đã nạp ETL và đã chạy `python -m src.olap.build`; nếu không có thì bỏ qua.
Phụ trách: P2
"""
import pytest
from sqlalchemy import text
from streamlit.testing.v1 import AppTest

from src.common.config import ROOT_DIR

PAGES = ROOT_DIR / "src" / "app" / "pages"
TIMEOUT = 120


@pytest.fixture(scope="module", autouse=True)
def _require_db():
    from src.common.db import get_engine
    try:
        with get_engine().connect() as conn:
            n = conn.execute(text("SELECT count(*) FROM olap.mv_sales_cube")).scalar()
    except Exception as e:
        pytest.skip(f"Chưa có DB / view olap: {type(e).__name__}")
    if not n:
        pytest.skip("olap rỗng")


def run(page: str) -> AppTest:
    return AppTest.from_file(str(PAGES / page), default_timeout=TIMEOUT).run()


def assert_clean(at: AppTest) -> None:
    assert not at.exception, [e.value for e in at.exception]
    assert not at.error, [e.value for e in at.error]


@pytest.mark.parametrize("page", sorted(p.name for p in PAGES.glob("*.py")))
def test_page_renders_without_error(page):
    assert_clean(run(page))


def test_overview_kpis_are_consistent_with_warehouse():
    at = run("1_Tong_quan.py")
    kpi = {m.label: m.value for m in at.metric}
    assert kpi["Số đơn"] != "0"
    assert kpi["Tỷ lệ giao trễ"].endswith("%")


def test_olap_explorer_drilldown_and_pivot():
    at = run("4_OLAP_explorer.py")
    assert_clean(at)
    at.segmented_control(key="olap_depth").set_value("Năm › Quý › Tháng").run()   # drill-down
    assert_clean(at)
    assert list(at.dataframe[0].value.columns)[:3] == ["Năm", "Quý", "Tháng"]
    at.segmented_control(key="olap_view").set_value("Tự chọn chiều").run()
    ms = {m.label: m for m in at.multiselect}
    ms["Chiều ở hàng"].set_value(["category"]).run()
    ms = {m.label: m for m in at.multiselect}
    ms["Chiều ở cột (pivot)"].set_value(["customer_region"]).run()
    assert_clean(at)
    assert "Đông Nam (Sudeste)" in at.dataframe[0].value.columns


def test_dss_recommendation_changes_with_target():
    at = run("6_DSS_ngay_hen_giao.py")
    assert_clean(at)
    loose = next(m.value for m in at.metric if m.label == "Gợi ý ngày hẹn")
    at.sidebar.slider[0].set_value(1).run()                   # mục tiêu trễ 1% chặt hơn 5%
    assert_clean(at)
    strict = next(m.value for m in at.metric if m.label == "Gợi ý ngày hẹn")
    assert int(strict.split()[0]) > int(loose.split()[0])


def _metric(at: AppTest, label: str) -> float:
    return float(next(m.value for m in at.metric if m.label == label).replace(",", ""))


def test_ml_intervention_page_runs_p3_models():
    pytest.importorskip("src.dss.whatif", reason="Chưa có code P3")
    from src.dss import whatif
    if not hasattr(whatif, "score_orders"):
        pytest.skip("Chưa có code P3")
    import json

    from src.common.config import ARTIFACTS_DIR
    from src.ml.late_risk import BUNDLE_VERSION
    runs = [p.parent for p in (ARTIFACTS_DIR / "models" / "late_risk").glob("*/seller_history.joblib")
            if json.loads((p.parent / "manifest.json").read_text()).get("format_version") == BUNDLE_VERSION]
    if not runs:
        pytest.skip("Chưa train model P3 (phiên bản hiện tại)")
    at = AppTest.from_file(str(PAGES / "7_DSS_can_thiep_ML.py"), default_timeout=600).run()
    assert_clean(at)
    picked = _metric(at, "Đơn nên can thiệp")
    assert 0 < picked <= 20                                     # năng lực mặc định 20 đơn/ngày
    assert any(m.label == "Đơn có nhóm khách" for m in at.metric)   # có phần ảnh hưởng của K-Means
    at.toggle(key="dss_use_segments").set_value(False).run()    # bỏ nhóm khách: mọi hệ số bằng 1
    assert_clean(at)
    assert not any(m.label == "Đơn có nhóm khách" for m in at.metric)
    at.toggle(key="dss_use_segments").set_value(True).run()
    at.toggle(key="dss_unlimited").set_value(True).run()        # không giới hạn số đơn
    assert_clean(at)
    assert _metric(at, "Đơn nên can thiệp") >= picked
    at.number_input(key="dss_cost").set_value(1000.0).run()     # chi phí rất cao: không đơn nào đáng can thiệp
    assert_clean(at)
    assert _metric(at, "Đơn nên can thiệp") == 0
    at.segmented_control(key="dss_model").set_value("random_forest").run()
    assert_clean(at)
