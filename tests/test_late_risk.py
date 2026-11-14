"""Focused checks for leakage, resampling, selection and what-if."""

import joblib
import numpy as np
import pandas as pd
import pytest
from sklearn.dummy import DummyClassifier

from src.dss.whatif import build_scenario, run_whatif, summarize
from src.ml.late_risk import (
    CATEGORICAL,
    FEATURES,
    HISTORY,
    MODEL_NAMES,
    NUMERIC,
    choose_method,
    prepare_orders,
    resample_train,
    select_threshold,
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


def test_threshold_maximizes_recall_with_precision_floor():
    y = np.array([1, 0, 1, 0, 1, 0])
    scores = np.array([0.9, 0.8, 0.7, 0.6, 0.5, 0.4])
    chosen = select_threshold(y, scores)
    assert chosen["threshold"] == 0.5
    assert chosen["precision"] == 0.6
    assert chosen["recall"] == 1
    assert select_threshold([0, 1], [0.5, 0.5]) is None
    a = dict(chosen, method="SMOTE")
    b = dict(chosen, method="SMOTENC")
    assert choose_method([b, a])["method"] == "SMOTE"
    b["precision"] = 0.7
    assert choose_method([a, b])["method"] == "SMOTENC"
    assert choose_method([None]) is None


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


def test_whatif_zero_and_date_validation(tmp_path):
    from sklearn.compose import ColumnTransformer
    from sklearn.preprocessing import OneHotEncoder

    data = orders()
    encoder = ColumnTransformer(
        [
            ("numeric", "passthrough", NUMERIC),
            ("category", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL),
        ]
    )
    x = encoder.fit_transform(data[FEATURES])
    model = DummyClassifier(strategy="prior").fit(x, [0, 0, 1, 1])
    for name in MODEL_NAMES:
        joblib.dump(
            {
                "model": model,
                "encoder": encoder,
                "threshold": 0.4,
                "fold": 2,
                "seed": 42,
            },
            tmp_path / f"{name}.joblib",
        )
    result = run_whatif(tmp_path, data, 0)
    assert len(result) == 6 * len(data)
    assert result.risk_delta.eq(0).all()
    summary = summarize(result)
    assert summary.alerts_before.equals(summary.alerts_after)
    assert summary[["on_time_to_late", "late_to_on_time"]].sum().sum() == 0
    scenario = build_scenario(data, 3)
    assert scenario.shipping_days_estimated.eq(13).all()
    pd.testing.assert_frame_equal(scenario[HISTORY], data[HISTORY])
    for days in [-11, True, 1.5]:
        with pytest.raises(ValueError):
            build_scenario(data, days)
    for invalid in [
        pd.concat([data, data]),
        data.drop(columns=["distance_km"]),
    ]:
        with pytest.raises(ValueError):
            prepare_orders(invalid)
    data.loc[0, "distance_km"] = np.inf
    with pytest.raises(ValueError):
        prepare_orders(data)
