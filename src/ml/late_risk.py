"""Train three late-risk models on one validation-selected Olist fold."""

import argparse
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from imblearn.over_sampling import SMOTE, SMOTENC
from imblearn.under_sampling import RandomUnderSampler
from lightgbm import LGBMClassifier
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sqlalchemy import text

from src.common.db import get_engine

SEED = 42
MODEL_NAMES = ("logistic_regression", "random_forest", "lightgbm")
LR_C = (1, 1, 10, 0.001, 0.1)

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
    ].max(axis=1)
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


def make_models(fold):
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
                C=LR_C[fold - 1],
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
    data = prepare_orders(orders)
    x = bundle["encoder"].transform(data[FEATURES]).astype(np.float32)
    probability = bundle["model"].predict_proba(x)[:, 1]
    return pd.DataFrame(
        {
            "order_id": data.order_id.to_numpy(),
            "p_late": probability,
            "risk_score": probability,
            "threshold": bundle["threshold"],
            "predicted_label": (probability >= bundle["threshold"]).astype(
                int
            ),
        }
    )


def train(output_dir):
    """Fit the selected fold 4 models on the full outer training split."""
    output = Path(output_dir)
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(
            "Use an empty output directory for this training run"
        )
    engine = get_engine()
    try:
        with engine.connect().execution_options(
            isolation_level="REPEATABLE READ"
        ) as connection:
            data, links = load_orders(connection)
    finally:
        engine.dispose()
    y = data.is_late.to_numpy(int)
    folds = list(
        StratifiedKFold(
            n_splits=5,
            shuffle=True,
            random_state=SEED,
        ).split(data, y)
    )
    fold = 4
    train_idx, test_idx = folds[fold - 1]
    assert not np.intersect1d(train_idx, test_idx).size
    fit = data.iloc[train_idx]
    train_features = seller_history(fit, fit, links)
    test_features = seller_history(data.iloc[test_idx], fit, links)
    bundles = {}
    for method, names in (
        ("SMOTE", ["logistic_regression"]),
        ("SMOTENC", ["random_forest", "lightgbm"]),
    ):
        encoder, x, labels = resample_train(
            train_features, y[train_idx], method
        )
        for name in names:
            model = make_models(fold)[name]
            model.fit(x, labels)
            bundle = {
                "model": model,
                "encoder": encoder,
                "method": method,
                "threshold": 0.4,
                "fold": fold,
                "seed": SEED,
                "train_counts": [10_000, 10_000],
            }
            predicted = predict_late(bundle, test_features)
            print(
                f"\nTEST | {name} | {method} | "
                f"threshold={bundle['threshold']:.6f}"
            )
            print(
                classification_report(
                    y[test_idx],
                    predicted.predicted_label,
                    labels=[0, 1],
                    target_names=["On time", "Late"],
                    digits=4,
                    zero_division=0,
                )
            )
            print(
                f"AUC={roc_auc_score(y[test_idx], predicted.risk_score):.6f}",
                flush=True,
            )
            bundles[name] = bundle
    output.mkdir(parents=True, exist_ok=True)
    for name, bundle in bundles.items():
        path = output / f"{name}.joblib"
        joblib.dump(bundle, path)
        np.testing.assert_allclose(
            predict_late(bundle, test_features).p_late,
            predict_late(joblib.load(path), test_features).p_late,
            rtol=1e-12,
            atol=1e-14,
        )
    history_columns = [
        "order_id",
        "order_delivered_customer_date",
        "order_estimated_delivery_date",
        "is_late",
        "delay_days",
    ]
    joblib.dump(
        {
            "train": fit[history_columns],
            "links": links.loc[links.order_id.isin(fit.order_id)],
        },
        output / "seller_history.joblib",
    )
    manifest = {
        "fold": fold,
        "seed": SEED,
        "train_counts": [10_000, 10_000],
        "models": {
            name: {key: bundle[key] for key in ("method", "threshold")}
            for name, bundle in bundles.items()
        },
        "splits": {
            key: data.iloc[idx].order_id.tolist()
            for key, idx in {
                "train": train_idx,
                "test": test_idx,
            }.items()
        },
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    prepare_orders(test_features.head(20)).to_csv(
        output / "example_orders.csv", index=False
    )
    print(
        f"Saved models and reproducible splits: {output.resolve()}", flush=True
    )
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    train(args.output_dir)
