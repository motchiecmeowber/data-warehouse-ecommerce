"""Focused checks for leakage, resampling, selection and what-if."""

import joblib
import numpy as np
import pandas as pd
import pytest
from sklearn.dummy import DummyClassifier

from src.dss.whatif import evaluate, plot_tornado, run_whatif, score_orders
from src.ml.late_risk import (
    CATEGORICAL,
    FEATURES,
    HISTORY,
    MODEL_NAMES,
    NUMERIC,
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
    bundle = dict(encoder=encoder, model=model, threshold=0.4)
    assert predict_late(bundle, data).p_late.eq(0.5).all()
    for name in MODEL_NAMES:
        joblib.dump(bundle, tmp_path / f"{name}.joblib")
    scored = score_orders(tmp_path, data, segments, {"A": 2})
    assert len(scored) == 12 and scored.p_late.eq(0.5).all()
    assert scored.factor.tolist() == [2, 2, 1, 1] * 3
    with pytest.raises(ValueError):
        score_orders(tmp_path, data, pd.concat([segments, segments]), {"A": 2})
