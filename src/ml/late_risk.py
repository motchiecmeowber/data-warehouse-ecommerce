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
from sklearn.metrics import classification_report, precision_recall_curve
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedKFold, train_test_split
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
SELECT f.order_id, f.order_purchase_timestamp,
       t.order_delivered_customer_date, t.order_estimated_delivery_date,
       f.promised_days AS shipping_days_estimated,
       f.is_late, f.delay_days,
       totals.freight_value, totals.item_physical_score, totals.distance_km,
       categories.product_category_name
FROM dw.fact_order_fulfillment f
JOIN staging.orders_typed t ON t.order_id = f.order_id
JOIN totals ON totals.order_id = f.order_id
LEFT JOIN categories
    ON categories.order_id = f.order_id AND categories.rank = 1
WHERE f.is_late IS NOT NULL
ORDER BY f.order_id
"""

LINKS_QUERY = """
SELECT DISTINCT f.order_id, s.seller_id
FROM dw.fact_sales f
JOIN dw.dim_seller s ON s.seller_key = f.seller_key
WHERE s.seller_id IS NOT NULL
ORDER BY f.order_id, s.seller_id
"""


def load_orders(connection):
    """Read ETL-cleaned warehouse features and exact milestone timestamps."""
    data = pd.read_sql_query(text(QUERY), connection)
    links = pd.read_sql_query(text(LINKS_QUERY), connection)
    for col in [
        "order_purchase_timestamp",
        "order_delivered_customer_date",
        "order_estimated_delivery_date",
    ]:
        data[col] = pd.to_datetime(data[col])
    purchase = data.order_purchase_timestamp
    data["order_weekday"] = purchase.dt.dayofweek
    data["order_purchase_month"] = purchase.dt.month
    static = [col for col in FEATURES if col not in HISTORY]
    data = data.dropna(subset=static).reset_index(drop=True)
    if data.empty or not data.order_id.is_unique:
        raise ValueError("DW must contain eligible orders with unique IDs")
    data["is_late"] = data.is_late.astype(int)
    if set(data.is_late.unique()) != {0, 1}:
        raise ValueError("DW must contain both on-time and late orders")
    if not data.order_id.isin(links.order_id).all():
        raise ValueError("Missing seller links for eligible orders")
    return data, links


def balanced_indices(indices, y, seed):
    """Keep every real late order and sample equally many on-time orders."""
    late = indices[y[indices] == 1]
    ontime = indices[y[indices] == 0]
    if not 0 < len(late) <= len(ontime):
        raise ValueError("Cannot form a real 50:50 evaluation set")
    rng = np.random.default_rng(seed)
    return np.sort(np.r_[late, rng.choice(ontime, len(late), replace=False)])


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


def select_threshold(y, probability):
    """Maximize recall subject to precision >= 0.60; never relax it."""
    precision, recall, thresholds = precision_recall_curve(y, probability)
    valid = np.flatnonzero(precision[:-1] >= 0.60)
    if not len(valid):
        return None
    f1 = (
        2
        * precision[:-1]
        * recall[:-1]
        / np.maximum(
            precision[:-1] + recall[:-1],
            np.finfo(float).eps,
        )
    )
    best = max(valid, key=lambda i: (recall[i], f1[i], thresholds[i]))
    return {
        "threshold": float(thresholds[best]),
        "precision": float(precision[best]),
        "recall": float(recall[best]),
        "f1": float(f1[best]),
    }


def choose_method(candidates):
    valid = [item for item in candidates if item is not None]
    if not valid:
        return None
    return max(
        valid,
        key=lambda item: (
            item["recall"],
            item["precision"],
            item["method"] == "SMOTE",
        ),
    )


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
    expected_days = (
        (data.order_estimated_delivery_date - purchase).dt.total_seconds()
        / 86400
    ).round(2)
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
            "risk_score": probability,
            "threshold": bundle["threshold"],
            "predicted_label": (probability >= bundle["threshold"]).astype(
                int
            ),
        }
    )


def train(output_dir):
    """Select on validation, then refit and evaluate one common outer fold."""
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
    choices = []
    for fold, (train_idx, test_idx) in enumerate(folds, 1):
        fit_idx, val_pool = train_test_split(
            train_idx,
            test_size=0.2,
            stratify=y[train_idx],
            random_state=SEED,
        )
        val_idx = balanced_indices(val_pool, y, SEED + fold)
        assert not np.intersect1d(fit_idx, val_pool).size
        assert not np.intersect1d(train_idx, test_idx).size
        fit = seller_history(data.iloc[fit_idx], data.iloc[fit_idx], links)
        validation = seller_history(
            data.iloc[val_idx], data.iloc[fit_idx], links
        )
        candidates = {name: [] for name in MODEL_NAMES}
        for method in ("SMOTE", "SMOTENC"):
            encoder, x, labels = resample_train(fit, y[fit_idx], method)
            x_val = encoder.transform(validation[FEATURES]).astype(np.float32)
            for name, model in make_models(fold).items():
                model.fit(x, labels)
                selected = select_threshold(
                    y[val_idx], model.predict_proba(x_val)[:, 1]
                )
                if selected is not None:
                    selected.update(method=method, model=name)
                candidates[name].append(selected)
                print(
                    f"Fold {fold} | {method} | {name}: {selected}", flush=True
                )
        selected = {
            name: choose_method(items) for name, items in candidates.items()
        }
        if all(item is not None for item in selected.values()):
            choices.append(
                {
                    "fold": fold,
                    "models": selected,
                    "recall": np.mean(
                        [item["recall"] for item in selected.values()]
                    ),
                    "precision": np.mean(
                        [item["precision"] for item in selected.values()]
                    ),
                    "fit_idx": fit_idx,
                    "val_pool": val_pool,
                    "val_idx": val_idx,
                }
            )
    if not choices:
        raise RuntimeError(
            "No fold satisfies validation precision >= 60% for all models"
        )
    best = max(
        choices,
        key=lambda item: (item["recall"], item["precision"], -item["fold"]),
    )
    fold = best["fold"]
    train_idx, test_pool = folds[fold - 1]
    test_idx = balanced_indices(test_pool, y, SEED + fold)
    train_features = seller_history(
        data.iloc[train_idx], data.iloc[train_idx], links
    )
    test_features = seller_history(
        data.iloc[test_idx], data.iloc[train_idx], links
    )
    print(
        f"Selected fold {fold}; mean validation recall={best['recall']:.6f}",
        flush=True,
    )
    bundles = {}
    for method in ("SMOTE", "SMOTENC"):
        names = [
            name
            for name in MODEL_NAMES
            if best["models"][name]["method"] == method
        ]
        if not names:
            continue
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
        np.testing.assert_array_equal(
            predict_late(bundle, test_features).risk_score,
            predict_late(joblib.load(path), test_features).risk_score,
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
            "train": data.iloc[train_idx][history_columns],
            "links": links.loc[
                links.order_id.isin(data.iloc[train_idx].order_id)
            ],
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
                "test_pool": test_pool,
                "test": test_idx,
                "fit": best["fit_idx"],
                "validation_pool": best["val_pool"],
                "validation": best["val_idx"],
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
