"""Focused checks for leakage, resampling, selection and what-if."""

import json
from unittest.mock import MagicMock

import joblib
import numpy as np
import pandas as pd
import pytest
from sklearn.dummy import DummyClassifier
from sklearn.calibration import CalibratedClassifierCV
from sklearn.frozen import FrozenEstimator

from src.dss.whatif import evaluate, plot_tornado, run_whatif, score_orders
from src.ml import late_risk
from src.ml.late_risk import (
    CATEGORICAL,
    FEATURES,
    HISTORY,
    MODEL_NAMES,
    NUMERIC,
    load_orders,
    predict_late,
    prepare_orders,
    resample_train,
    seller_history,
)


def orders(n=4):
    data = pd.DataFrame({col: np.ones(n) for col in NUMERIC})
    data["order_id"] = [f"o{i}" for i in range(n)]
    data["order_purchase_timestamp"] = pd.Timestamp("2020-01-01")
    data["order_estimated_delivery_date"] = pd.Timestamp("2020-01-11")
    data["shipping_days_estimated"] = 10.0
    data["order_weekday"] = 2
    data["order_purchase_month"] = 1
    data["product_category_name"] = [
        "books" if i % 2 else "toys" for i in range(n)
    ]
    return data


@pytest.mark.parametrize("method", ["SMOTE", "SMOTENC"])
def test_resampling_and_unseen_category(method):
    data = orders(10_008)
    y = np.r_[np.zeros(10_000, dtype=int), np.ones(8, dtype=int)]
    encoder, x, labels = resample_train(data, y, method)
    assert np.bincount(labels).tolist() == [10_000, 10_000]
    assert np.isfinite(x).all()
    if method == "SMOTENC":
        start = len(NUMERIC)
        category_values = x[:, start:]
        assert set(np.unique(category_values)) <= {0, 1}
        np.testing.assert_array_equal(category_values.sum(axis=1), 1)
    new = data.head(1).copy()
    new["product_category_name"] = "unseen"
    assert encoder.transform(new[FEATURES]).shape[1] == x.shape[1]
    assert (
        "unseen" not in encoder.named_transformers_["category"].categories_[0]
    )


def test_seller_history_uses_only_known_training_outcomes():
    train = pd.DataFrame(
        {
            "order_id": ["old", "future"],
            "order_delivered_customer_date": pd.to_datetime(
                ["2020-01-02", "2020-01-20"]
            ),
            "order_estimated_delivery_date": pd.to_datetime(
                ["2020-01-01", "2020-01-19"]
            ),
            "is_late": [1, 1],
            "delay_days": [1, 1],
        }
    )
    query = pd.DataFrame(
        {
            "order_id": ["q1", "q2", "q3"],
            "order_purchase_timestamp": pd.to_datetime(
                ["2020-01-02", "2020-01-03", "2020-01-03"]
            ),
        }
    )
    links = pd.DataFrame(
        {
            "order_id": ["old", "future", "q1", "q2", "q3"],
            "seller_id": ["s", "s", "s", "s", "new"],
        }
    )
    result = seller_history(query, train, links)
    assert result[HISTORY[0]].tolist() == [0, 1, 0]
    assert result[HISTORY[1]].tolist() == [0, 100, 0]
    changed = train.copy()
    changed.loc[1, ["is_late", "delay_days"]] = [0, -50]
    pd.testing.assert_frame_equal(
        result, seller_history(query, changed, links)
    )


def test_intervention_scenarios(tmp_path):
    scores = pd.DataFrame(
        {
            "order_id": ["b", "a", "c"],
            "p_late": [0.5, 0.5, 0.25],
            "factor": [1, 1, 2],
            "model": "lightgbm",
        }
    )
    links = pd.DataFrame(
        {
            "order_id": ["a", "a", "b", "c"],
            "seller_id": ["x", "y", "y", "x"],
            "seller_state": "SP",
            "customer_state": "RJ",
        }
    )
    tables = run_whatif(scores, links, 100, [20, 25], [0.5], [1, 0, 20])
    base = tables["orders"].query("cost == 20 and capacity == 1")
    assert base.order_id.tolist() == ["a", "b", "c"]
    assert base.selected.tolist() == [True, False, False]
    summary = tables["summary"].query("cost == 20 and capacity == 1").iloc[0]
    assert (summary.avoided_late, summary.gross, summary.net) == (0.25, 25, 5)
    for key in ["sellers", "routes"]:
        grouped = tables[key].query("cost == 20 and capacity == 1")
        assert grouped.orders.sum() == 3
        assert grouped.selected_net.sum() == 5
        assert grouped.expected_late.sum() == 1.25
    assert (
        not tables["orders"]
        .query("cost == 25 or capacity == 0")
        .selected.any()
    )
    assert evaluate(scores, 100, 0, 1).selected.all()
    assert not evaluate(scores, 100, 0, 0).selected.any()
    assert evaluate(scores, 100, 20, 0.5, 20).selected.all()
    tornado = tables["sensitivity"]
    assert tornado.query("parameter == 'cost'").net.tolist() == [9, 1]
    assert tornado.query("parameter == 'efficacy'").net.tolist() == [0, 10]
    assert tornado.query("parameter == 'loss'").net.tolist() == [0, 10]
    plot_tornado(tornado, tmp_path / "tornado.png")
    assert (tmp_path / "tornado.png").stat().st_size > 0


def test_raw_scoring_and_segments(tmp_path):
    from sklearn.compose import ColumnTransformer
    from sklearn.preprocessing import OneHotEncoder

    data = orders()
    data["customer_unique_id"] = ["u", "u", "v", "w"]
    segments = pd.DataFrame(
        {"customer_unique_id": ["u"], "kmeans_segment": ["A"]}
    )
    encoder = ColumnTransformer(
        [
            ("numeric", "passthrough", NUMERIC),
            ("category", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL),
        ]
    )
    x = encoder.fit_transform(data[FEATURES])
    model = DummyClassifier(strategy="prior").fit(x, [0, 0, 1, 1])
    bundle = dict(encoder=encoder, model=model, threshold=0.4,
                  format_version=2, available_at="2019-01-01",
                  calibrator=CalibratedClassifierCV(FrozenEstimator(model), cv=2).fit(x, [0, 0, 1, 1]))
    segments.attrs["snapshot"] = {"as_of": "2019-01-01"}
    (tmp_path / "manifest.json").write_text(json.dumps(dict(
        format_version=2, available_at="2019-01-01", splits=dict(train=[], calibration=[]))))
    assert predict_late(bundle, data).p_late.eq(0.5).all()
    changed = data.assign(is_late=[1, 0, 1, 0],
                          order_delivered_customer_date=pd.Timestamp("2030-01-01"))
    pd.testing.assert_frame_equal(predict_late(bundle, data), predict_late(bundle, changed))
    for name in MODEL_NAMES:
        joblib.dump(bundle, tmp_path / f"{name}.joblib")
    scored = score_orders(tmp_path, data, segments, {"A": 2})
    assert len(scored) == 12 and scored.p_late.eq(0.5).all()
    assert scored.factor.tolist() == [2, 2, 1, 1] * 3
    future = segments.copy()
    future.attrs["snapshot"] = {"as_of": "2021-01-01"}
    with pytest.raises(ValueError, match="snapshot"):
        score_orders(tmp_path, data, future, {"A": 2})
    manifest_path = tmp_path / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["available_at"] = "2021-01-01"
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="artifact"):
        score_orders(tmp_path, data, segments, {"A": 2})
    manifest["available_at"] = "2019-01-01"
    manifest["splits"]["calibration"] = ["o0"]
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="overlap"):
        score_orders(tmp_path, data, segments, {"A": 2})
    manifest["splits"]["calibration"] = []
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError):
        score_orders(tmp_path, data, pd.concat([segments, segments]), {"A": 2})


def test_warehouse_half_centiday_rounding(monkeypatch):
    rows = orders(3)
    rows["order_estimated_delivery_date"] = (
        rows.order_purchase_timestamp + pd.Timedelta(seconds=1659312)
    )
    rows.loc[2, "order_estimated_delivery_date"] = (
        rows.order_purchase_timestamp[2] - pd.Timedelta(seconds=1)
    )
    rows["shipping_days_estimated"] = 19.21
    rows["order_delivered_customer_date"] = rows.order_estimated_delivery_date
    rows["is_late"] = [0, 1, 0]
    replies = iter([rows, rows[["order_id"]].assign(seller_id="s")])
    monkeypatch.setattr(pd, "read_sql_query", lambda *a, **kw: next(replies))
    loaded, _ = load_orders(None)
    assert prepare_orders(loaded).shipping_days_estimated.tolist() == [
        19.2,
        19.2,
    ]


@pytest.mark.parametrize(
    "drift, fails",
    [(np.spacing(0.5), False), (0.01, True)],
    ids=["roundoff", "material-change"],
)
def test_train_model_roundtrip_tolerance(tmp_path, monkeypatch, drift, fails):
    from sklearn.compose import ColumnTransformer
    from sklearn.preprocessing import OneHotEncoder

    data = orders(60)
    for i, date in enumerate(["2017-06-01", "2018-02-01", "2018-05-01"]):
        idx = data.index[i*20:(i+1)*20]
        data.loc[idx, "order_purchase_timestamp"] = pd.Timestamp(date)
    data["order_estimated_delivery_date"] = data.order_purchase_timestamp + pd.Timedelta(days=10)
    data["order_weekday"] = data.order_purchase_timestamp.dt.dayofweek
    data["order_purchase_month"] = data.order_purchase_timestamp.dt.month
    data["is_late"] = np.arange(len(data)) % 2
    data.loc[20:39, "is_late"] = (np.arange(20) % 4 == 0).astype(int)
    data["delay_days"] = data.is_late
    data["order_delivered_customer_date"] = (data.order_estimated_delivery_date
        + pd.to_timedelta(data.delay_days, unit="D"))
    links = data[["order_id"]].assign(seller_id="s")
    monkeypatch.setattr(late_risk, "get_engine", MagicMock())
    monkeypatch.setattr(late_risk, "load_orders", lambda connection: (data, links))
    encoder = ColumnTransformer(
        [
            ("numeric", "passthrough", NUMERIC),
            ("category", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL),
        ]
    ).fit(data[FEATURES])
    def resample(features, y, method):
        assert features.order_id.tolist() == data.order_id.iloc[:20].tolist()
        return encoder, encoder.transform(features[FEATURES]), y

    monkeypatch.setattr(late_risk, "resample_train", resample)
    original_calibrator = late_risk.CalibratedClassifierCV
    calibrated = []

    original_fit = original_calibrator.fit

    def checked_fit(self, x, y, **kwargs):
        assert len(x) == 20 and sum(y) == 5
        assert isinstance(self.estimator, FrozenEstimator)
        calibrated.append(True)
        return original_fit(self, x, y, **kwargs)

    monkeypatch.setattr(original_calibrator, "fit", checked_fit)
    monkeypatch.setattr(
        late_risk,
        "make_models",
        lambda: {
            name: DummyClassifier(strategy="prior") for name in MODEL_NAMES
        },
    )
    original_load = joblib.load

    def load_with_drift(path):
        bundle = original_load(path)
        if path.name == "random_forest.joblib":
            bundle["model"].class_prior_[1] += drift
        return bundle

    monkeypatch.setattr(joblib, "load", load_with_drift)
    output = tmp_path / "models"
    if fails:
        with pytest.raises(AssertionError):
            late_risk.train(output)
        assert not (output / "manifest.json").exists()
    else:
        manifest = late_risk.train(output)
        expected = {f"{name}.joblib" for name in MODEL_NAMES} | {
            "seller_history.joblib", "manifest.json", "example_orders.csv",
            "metrics.csv", "predictions.csv"
        }
        assert {path.name for path in output.iterdir()} == expected
        assert set(manifest["models"]) == set(MODEL_NAMES)
        assert len(calibrated) == 3
        assert manifest["counts"]["calibration"]["late"] == 5


def test_temporal_windows_and_unknown_outcomes():
    data = pd.DataFrame({
        "order_id": list("abcdefghij"),
        "order_purchase_timestamp": pd.to_datetime([
            "2017-01-01", "2017-01-01", "2018-02-01", "2018-02-01",
            "2018-05-01", "2018-05-01", "2018-01-31", "2018-04-30",
            "2018-09-01", "2016-12-31"]),
        "is_late": [0, 1] * 5,
    })
    data["order_estimated_delivery_date"] = data.order_purchase_timestamp + pd.Timedelta(days=5)
    data["order_delivered_customer_date"] = data.order_estimated_delivery_date
    parts = late_risk.temporal_splits(data, late_risk.load_yaml("ml.yaml"))
    assert {k: v.order_id.tolist() for k, v in parts.items()} == {
        "train": ["a", "b"], "calibration": ["c", "d"], "test": ["e", "f"]}
    assert late_risk.best_threshold([0, 1, 0, 1], [0.1, 0.2, 0.3, 0.4]) == 0.2
    assert late_risk.best_threshold([1, 0, 0, 1], [0.1, 0.2, 0.3, 0.4]) == 0.4


@pytest.mark.parametrize("column,value", [("p_late", -0.1), ("p_late", 1.1),
                                           ("p_late", np.nan), ("factor", -1), ("factor", np.inf)])
def test_invalid_decision_scores(column, value):
    scores = pd.DataFrame(dict(order_id=["o"], model=["m"], p_late=[0.2], factor=[1.0]))
    scores.loc[0, column] = value
    with pytest.raises(ValueError):
        evaluate(scores, 100, 2, 0.25)


def test_duplicate_scores_and_legacy_bundle():
    scores = pd.DataFrame(dict(order_id=["o", "o"], model=["m", "m"],
                               p_late=[0.2, 0.2], factor=[1, 1]))
    with pytest.raises(ValueError):
        evaluate(scores, 100, 2, 0.25)
    with pytest.raises(ValueError, match="retrain"):
        predict_late({}, orders())
