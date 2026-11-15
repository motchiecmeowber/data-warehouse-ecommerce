"""Train and calibrate late-risk models on disjoint chronological windows."""

import argparse
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from imblearn.over_sampling import SMOTE, SMOTENC
from imblearn.under_sampling import RandomUnderSampler
from lightgbm import LGBMClassifier
from sklearn.calibration import CalibratedClassifierCV
from sklearn.compose import ColumnTransformer
from sklearn.frozen import FrozenEstimator
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (average_precision_score, brier_score_loss,
                             confusion_matrix, f1_score, log_loss,
                             precision_recall_curve, precision_score,
                             recall_score, roc_auc_score)
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sqlalchemy import text

from src.common.db import get_engine
from src.common.config import load_yaml

SEED = 42
MODEL_NAMES = ("logistic_regression", "random_forest", "lightgbm")
BUNDLE_VERSION = 2

HISTORY = [
    "delayed_orders_by_seller",
    "delay_rate_percent_by_seller",
    "seller_avg_delay_days",
]
NUMERIC = [
    "distance_km",
    "freight_value",
    "shipping_days_estimated",
    "order_weekday",
    "order_purchase_month",
    "item_physical_score",
] + HISTORY
CATEGORICAL = ["product_category_name"]


def seller_history(query, train, links):
    events = train[
        [
            "order_id",
            "order_delivered_customer_date",
            "order_estimated_delivery_date",
            "is_late",
            "delay_days",
        ]
    ].copy()
    events["known_at"] = events[
        ["order_delivered_customer_date", "order_estimated_delivery_date"]
    ].max(axis=1).astype("datetime64[ns]")
    events = events.merge(links, on="order_id", validate="one_to_many")
    # Gộp đồng thời trước cumsum: mọi event tại cùng thời điểm cùng được biết.
    events = events.groupby(["seller_id", "known_at"], as_index=False).agg(
        n=("is_late", "size"),
        late=("is_late", "sum"),
        total_delay=("delay_days", "sum"),
    )
    events = events.sort_values(["known_at", "seller_id"])
    cols = ["n", "late", "total_delay"]
    events[cols] = events.groupby("seller_id")[cols].cumsum()
    queries = query[["order_id", "order_purchase_timestamp"]].merge(
        links, on="order_id", validate="one_to_many"
    )
    queries["order_purchase_timestamp"] = queries.order_purchase_timestamp.astype("datetime64[ns]")
    queries = queries.sort_values(["order_purchase_timestamp", "seller_id"])
    past = pd.merge_asof(
        queries,
        events,
        by="seller_id",
        left_on="order_purchase_timestamp",
        right_on="known_at",
        direction="backward",
        allow_exact_matches=False,
    )
    past[cols] = past[cols].fillna(0)
    past[HISTORY[0]] = past.late
    past[HISTORY[1]] = (100 * past.late / past.n.replace(0, np.nan)).fillna(0)
    past[HISTORY[2]] = (past.total_delay / past.n.replace(0, np.nan)).fillna(0)
    history = past.groupby("order_id")[HISTORY].mean()
    result = query.drop(columns=HISTORY, errors="ignore").join(
        history, on="order_id", validate="one_to_one"
    )
    assert result[HISTORY].notna().all().all(), "Đơn thiếu lịch sử seller"
    return result


FEATURES = NUMERIC + CATEGORICAL


QUERY = """
WITH items AS (
    SELECT s.order_id, seller.seller_id, s.quantity,
           s.freight_total,
           p.category_name_en AS product_category_name,
           p.weight_g * p.length_cm * p.height_cm * p.width_cm
               * s.quantity / 1000.0 AS item_physical_score,
           2 * 6371 * asin(sqrt(least(1.0, greatest(0.0,
               power(sin(radians(cg.latitude - sg.latitude) / 2), 2)
               + cos(radians(sg.latitude)) * cos(radians(cg.latitude))
               * power(sin(radians(cg.longitude - sg.longitude) / 2), 2)
           )))) AS distance_km,
           cg.latitude AS customer_lat, sg.latitude AS seller_lat,
           cg.longitude AS customer_lng, sg.longitude AS seller_lng
    FROM dw.fact_sales s
    JOIN dw.dim_product p ON p.product_key = s.product_key
    JOIN dw.dim_seller seller ON seller.seller_key = s.seller_key
    JOIN dw.dim_customer c ON c.customer_key = s.customer_key
    JOIN dw.dim_geography cg ON cg.geography_key = c.geography_key
    JOIN dw.dim_geography sg ON sg.geography_key = seller.geography_key
), categories AS (
    SELECT order_id, product_category_name,
           row_number() OVER (
               PARTITION BY order_id
               ORDER BY sum(quantity) DESC, product_category_name
           ) AS rank
    FROM items
    WHERE product_category_name IS NOT NULL
    GROUP BY order_id, product_category_name
), totals AS (
    SELECT order_id,
           CASE WHEN count(*) = count(freight_total)
                THEN sum(freight_total) END AS freight_value,
           CASE WHEN count(*) = count(item_physical_score)
                THEN sum(item_physical_score) END AS item_physical_score,
           CASE WHEN count(*) = count(customer_lat)
                  AND count(*) = count(seller_lat)
                  AND count(*) = count(customer_lng)
                  AND count(*) = count(seller_lng)
                THEN max(distance_km) END AS distance_km
    FROM items GROUP BY order_id
)
SELECT f.order_id, customer.customer_unique_id, f.order_purchase_timestamp,
       t.order_delivered_customer_date, t.order_estimated_delivery_date,
       f.is_late, f.delay_days,
       totals.freight_value, totals.item_physical_score, totals.distance_km,
       categories.product_category_name
FROM dw.fact_order_fulfillment f
JOIN dw.dim_customer customer ON customer.customer_key = f.customer_key
JOIN staging.orders_typed t ON t.order_id = f.order_id
JOIN totals ON totals.order_id = f.order_id
LEFT JOIN categories
    ON categories.order_id = f.order_id AND categories.rank = 1
WHERE f.is_late IS NOT NULL
ORDER BY f.order_id
"""

LINKS_QUERY = """
SELECT DISTINCT f.order_id, s.seller_id,
       sg.state_code AS seller_state, cg.state_code AS customer_state
FROM dw.fact_sales f
JOIN dw.dim_seller s ON s.seller_key = f.seller_key
JOIN dw.dim_customer c ON c.customer_key = f.customer_key
JOIN dw.dim_geography cg ON cg.geography_key = c.geography_key
JOIN dw.dim_geography sg ON sg.geography_key = s.geography_key
WHERE s.seller_id IS NOT NULL
ORDER BY f.order_id, s.seller_id
"""


def shipping_days(data):
    duration = (
        data.order_estimated_delivery_date - data.order_purchase_timestamp
    )
    seconds = duration.dt.total_seconds()
    return (seconds.where(seconds >= 0) / 86400).round(2)


def load_orders(connection, decision_day=None):
    """Read ETL-cleaned warehouse features and exact milestone timestamps."""
    query = QUERY
    params = {}
    if decision_day is not None:
        start = pd.Timestamp(decision_day).normalize()
        params = {"start": start, "end": start + pd.Timedelta(days=1)}
        query = query.replace(
            "WHERE f.is_late IS NOT NULL",
            "WHERE f.order_purchase_timestamp >= :start "
            "AND f.order_purchase_timestamp < :end",
        )
    data = pd.read_sql_query(text(query), connection, params=params)
    links = pd.read_sql_query(text(LINKS_QUERY), connection)
    for col in [
        "order_purchase_timestamp",
        "order_delivered_customer_date",
        "order_estimated_delivery_date",
    ]:
        data[col] = pd.to_datetime(data[col])
    purchase = data.order_purchase_timestamp
    data["shipping_days_estimated"] = shipping_days(data)
    data["order_weekday"] = purchase.dt.dayofweek
    data["order_purchase_month"] = purchase.dt.month
    static = [col for col in FEATURES if col not in HISTORY]
    data = data.dropna(subset=static).reset_index(drop=True)
    if data.empty or not data.order_id.is_unique:
        raise ValueError("DW must contain eligible orders with unique IDs")
    if decision_day is None:
        data["is_late"] = data.is_late.astype(int)
        if set(data.is_late.unique()) != {0, 1}:
            raise ValueError("DW must contain both on-time and late orders")
    else:
        data = data.drop(
            columns=[
                "is_late",
                "delay_days",
                "order_delivered_customer_date",
            ]
        )
    if not data.order_id.isin(links.order_id).all():
        raise ValueError("Missing seller links for eligible orders")
    return data, links.loc[links.order_id.isin(data.order_id)].copy()


def resample_train(features, y, method):
    """Fit preprocessing on train only and produce exactly 10k + 10k."""
    counts = np.bincount(np.asarray(y, dtype=int), minlength=2)
    if counts[0] < 10_000 or not 6 <= counts[1] <= 10_000:
        raise ValueError(f"Need >=10000 on-time and 6..10000 late: {counts}")
    if method not in ("SMOTE", "SMOTENC"):
        raise ValueError(f"Unknown resampling method: {method}")
    encoder = ColumnTransformer(
        [
            ("numeric", "passthrough", NUMERIC),
            (
                "category",
                OneHotEncoder(
                    handle_unknown="ignore",
                    sparse_output=False,
                ),
                CATEGORICAL,
            ),
        ]
    )
    if method == "SMOTE":
        encoded = encoder.fit_transform(features[FEATURES]).astype(np.float32)
        x, labels = RandomUnderSampler(
            sampling_strategy={0: 10_000},
            random_state=SEED,
        ).fit_resample(encoded, y)
        x, labels = SMOTE(
            sampling_strategy={1: 10_000},
            k_neighbors=5,
            random_state=SEED,
        ).fit_resample(x, labels)
    else:
        scaler = StandardScaler().fit(features[NUMERIC])
        mixed = features[FEATURES].copy()
        mixed[NUMERIC] = scaler.transform(mixed[NUMERIC])
        mixed[CATEGORICAL] = mixed[CATEGORICAL].astype(str)
        sampled, labels = RandomUnderSampler(
            sampling_strategy={0: 10_000},
            random_state=SEED,
        ).fit_resample(mixed, y)
        sampled, labels = SMOTENC(
            categorical_features=CATEGORICAL,
            sampling_strategy={1: 10_000},
            k_neighbors=5,
            random_state=SEED,
        ).fit_resample(sampled, labels)
        assert set(sampled.product_category_name) <= set(
            mixed.product_category_name
        )
        sampled[NUMERIC] = scaler.inverse_transform(sampled[NUMERIC])
        encoder.fit(features[FEATURES])
        x = encoder.transform(sampled[FEATURES]).astype(np.float32)
    assert np.bincount(labels).tolist() == [10_000, 10_000]
    return encoder, x, labels


def make_models():
    scaler = ColumnTransformer(
        [
            ("numeric", StandardScaler(), list(range(len(NUMERIC)))),
        ],
        remainder="passthrough",
    )
    return {
        "logistic_regression": make_pipeline(
            scaler,
            LogisticRegression(
                C=0.001,
                max_iter=2000,
                random_state=SEED,
            ),
        ),
        "random_forest": RandomForestClassifier(
            n_estimators=300,
            max_features=0.7,
            max_depth=None,
            min_samples_leaf=1,
            n_jobs=-1,
            random_state=SEED,
        ),
        "lightgbm": LGBMClassifier(
            n_estimators=100,
            learning_rate=0.03,
            num_leaves=63,
            min_child_samples=100,
            colsample_bytree=0.7,
            reg_lambda=0,
            n_jobs=2,
            verbosity=-1,
            random_state=SEED,
        ),
    }


def prepare_orders(orders):
    """Validate one feature row per order, without requiring its outcome."""
    required = [
        "order_id",
        "order_purchase_timestamp",
        "order_estimated_delivery_date",
    ] + FEATURES
    if not orders.columns.is_unique or orders.empty:
        raise ValueError("Need nonempty orders with unique column names")
    missing = sorted(set(required) - set(orders.columns))
    if missing:
        raise ValueError(f"Missing order columns: {missing}")
    data = orders[required].copy()
    data["order_id"] = data.order_id.astype("string").str.strip()
    if (
        data.order_id.isna().any()
        or data.order_id.eq("").any()
        or not data.order_id.is_unique
    ):
        raise ValueError("Order IDs must be nonempty and unique")
    for col in ["order_purchase_timestamp", "order_estimated_delivery_date"]:
        data[col] = pd.to_datetime(data[col], errors="coerce", format="mixed")
        if data[col].isna().any() or data[col].dt.tz is not None:
            raise ValueError(f"Invalid or timezone-aware timestamps: {col}")
    if (
        data.order_estimated_delivery_date < data.order_purchase_timestamp
    ).any():
        raise ValueError("Estimated delivery cannot precede purchase")
    for col in NUMERIC:
        data[col] = pd.to_numeric(data[col], errors="coerce")
    if not np.isfinite(data[NUMERIC].to_numpy(float)).all():
        raise ValueError("Numeric features must be finite")
    nonnegative = [col for col in NUMERIC if col != "seller_avg_delay_days"]
    if (data[nonnegative] < 0).any().any():
        raise ValueError("Negative feature value")
    if not data.delay_rate_percent_by_seller.between(0, 100).all():
        raise ValueError("Seller late rate must be in [0, 100]")
    category = data.product_category_name.astype("string").str.strip()
    if category.isna().any() or category.eq("").any():
        raise ValueError("Category must be nonempty")
    data["product_category_name"] = category
    purchase = data.order_purchase_timestamp
    expected_days = shipping_days(data)
    if not (
        np.allclose(data.shipping_days_estimated, expected_days, atol=1e-8)
        and data.order_weekday.eq(purchase.dt.dayofweek).all()
        and data.order_purchase_month.eq(purchase.dt.month).all()
    ):
        raise ValueError(
            "Date-derived features disagree with order timestamps"
        )
    return data


def predict_late(bundle, orders):
    if bundle.get("format_version") != BUNDLE_VERSION or "calibrator" not in bundle:
        raise ValueError("Uncalibrated/legacy model bundle; retrain late_risk")
    data = prepare_orders(orders)
    x = bundle["encoder"].transform(data[FEATURES]).astype(np.float32)
    raw = bundle["model"].predict_proba(x)[:, 1]
    probability = bundle["calibrator"].predict_proba(x)[:, 1]
    return pd.DataFrame(
        {
            "order_id": data.order_id.to_numpy(),
            "p_late": probability,
            "risk_score": raw,
            "threshold": bundle["threshold"],
            "predicted_label": (probability >= bundle["threshold"]).astype(
                int
            ),
        }
    )


def temporal_splits(data, config):
    """Exclude outcomes unavailable when each fitted artifact was created."""
    if data.empty or data.order_id.isna().any() or not data.order_id.is_unique:
        raise ValueError("Need nonempty labeled orders with unique IDs")
    split = config["split"]
    dates = {k: pd.Timestamp(v) for k, v in split.items()}
    if not (dates["train_start"] < dates["train_end"]
            == dates["calibration_start"] < dates["calibration_end"]
            == dates["test_start"] < dates["test_end"]):
        raise ValueError("Expected contiguous, increasing chronological windows")
    purchase = pd.to_datetime(data.order_purchase_timestamp)
    outcomes = data[["order_delivered_customer_date", "order_estimated_delivery_date"]]
    known = outcomes.max(axis=1)
    parts = {}
    for name in ("train", "calibration", "test"):
        mask = (purchase.ge(dates[f"{name}_start"])
                & purchase.lt(dates[f"{name}_end"]) & outcomes.notna().all(axis=1))
        if name != "test":
            mask &= known.lt(dates[f"{name}_end"])
        part = data.loc[mask].copy()
        if set(part.is_late.unique()) != {0, 1}:
            raise ValueError(f"{name} must contain both outcome classes")
        parts[name] = part
    return parts


def best_threshold(truth, probability):
    precision, recall, thresholds = precision_recall_curve(truth, probability)
    f1 = np.divide(2 * precision[:-1] * recall[:-1],
                   precision[:-1] + recall[:-1],
                   out=np.zeros(len(thresholds)),
                   where=(precision[:-1] + recall[:-1]) > 0)
    return float(thresholds[np.flatnonzero(f1 == f1.max())[-1]])


def fit_models(data, links, output_dir, config=None):
    """Shared fit/evaluation path for DW CLI and report reproduction."""
    config = load_yaml("ml.yaml") if config is None else config
    if config["random_state"] != SEED or tuple(config["models"]) != MODEL_NAMES:
        raise ValueError("This experiment requires seed 42 and the three configured models")
    output = Path(output_dir)
    if output.exists() and any(output.iterdir()):
        raise FileExistsError("Use an empty output directory for this training run")
    parts = temporal_splits(data, config)
    fit = parts["train"]
    features = {name: seller_history(part, fit, links)
                for name, part in parts.items()}
    train_features = features["train"]
    cal = prepare_orders(features["calibration"])
    test = features["test"]
    truth = test.is_late.to_numpy(int)
    available_at = str(pd.Timestamp(config["split"]["calibration_end"]))
    bundles, records, predictions = {}, [], []
    for method, names in (("SMOTE", ["logistic_regression"]),
                          ("SMOTENC", ["random_forest", "lightgbm"])):
        encoder, x, labels = resample_train(train_features, fit.is_late.to_numpy(int), method)
        x_cal = encoder.transform(cal[FEATURES]).astype(np.float32)
        for name in names:
            model = make_models()[name].fit(x, labels)
            calibrator = CalibratedClassifierCV(FrozenEstimator(model), method="sigmoid")
            calibrator.fit(x_cal, parts["calibration"].is_late.to_numpy(int))
            probability = calibrator.predict_proba(x_cal)[:, 1]
            threshold = best_threshold(parts["calibration"].is_late, probability)
            bundle = dict(model=model, encoder=encoder, calibrator=calibrator,
                          format_version=BUNDLE_VERSION, available_at=available_at,
                          method=method, threshold=threshold, seed=SEED,
                          train_counts=[10_000, 10_000])
            pred = predict_late(bundle, test)
            tn, fp, fn, tp = confusion_matrix(truth, pred.predicted_label, labels=[0, 1]).ravel()
            r = dict(model=name, method=method, threshold=threshold,
                     test_n=len(test), test_late=int(truth.sum()),
                     baseline_ap=float(truth.mean()),
                     auc=roc_auc_score(truth, pred.p_late),
                     raw_auc=roc_auc_score(truth, pred.risk_score),
                     average_precision=average_precision_score(truth, pred.p_late),
                     raw_average_precision=average_precision_score(truth, pred.risk_score),
                     precision=precision_score(truth, pred.predicted_label, zero_division=0),
                     recall=recall_score(truth, pred.predicted_label, zero_division=0),
                     f1=f1_score(truth, pred.predicted_label, zero_division=0),
                     brier=brier_score_loss(truth, pred.p_late),
                     raw_brier=brier_score_loss(truth, pred.risk_score),
                     log_loss=log_loss(truth, pred.p_late),
                     raw_log_loss=log_loss(truth, pred.risk_score),
                     tn=int(tn), fp=int(fp), fn=int(fn), tp=int(tp))
            records.append(r)
            predictions.append(pred.assign(model=name, truth=truth,
                                order_purchase_timestamp=test.order_purchase_timestamp.to_numpy()))
            bundles[name] = bundle
            print("TEST", r, flush=True)
    output.mkdir(parents=True, exist_ok=True)
    for name, bundle in bundles.items():
        path = output / f"{name}.joblib"
        joblib.dump(bundle, path)
        restored = predict_late(joblib.load(path), test)
        original = predict_late(bundle, test)
        np.testing.assert_allclose(original[["p_late", "risk_score"]],
                                   restored[["p_late", "risk_score"]], rtol=1e-12, atol=1e-14)
        np.testing.assert_array_equal(original.predicted_label, restored.predicted_label)
    history_columns = ["order_id", "order_delivered_customer_date",
                       "order_estimated_delivery_date", "is_late", "delay_days"]
    joblib.dump(dict(train=fit[history_columns],
                     links=links.loc[links.order_id.isin(fit.order_id)]),
                output / "seller_history.joblib")
    manifest = dict(format_version=BUNDLE_VERSION, seed=SEED,
                    available_at=available_at, config=config,
                    train_counts=[10_000, 10_000],
                    models={name: {k: bundle[k] for k in ("method", "threshold")}
                            for name, bundle in bundles.items()},
                    splits={name: part.order_id.tolist() for name, part in parts.items()},
                    counts={name: dict(orders=len(part), late=int(part.is_late.sum()),
                                       late_rate=float(part.is_late.mean()))
                            for name, part in parts.items()})
    metrics = pd.DataFrame(records)
    predicted = pd.concat(predictions, ignore_index=True)
    metrics.to_csv(output / "metrics.csv", index=False)
    predicted.to_csv(output / "predictions.csv", index=False)
    prepare_orders(test.head(20)).to_csv(output / "example_orders.csv", index=False)
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest, metrics, predicted


def train(output_dir):
    engine = get_engine()
    try:
        with engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection:
            data, links = load_orders(connection)
    finally:
        engine.dispose()
    manifest, _, _ = fit_models(data, links, output_dir)
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    train(args.output_dir)
