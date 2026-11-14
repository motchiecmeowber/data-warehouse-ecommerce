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

SEED = 42
MODEL_NAMES = ("logistic_regression", "random_forest", "lightgbm")
LR_C = (1, 1, 10, 0.001, 0.1)

FILES = {
    "orders": "olist_orders_dataset.csv",
    "items": "olist_order_items_dataset.csv",
    "customers": "olist_customers_dataset.csv",
    "sellers": "olist_sellers_dataset.csv",
    "products": "olist_products_dataset.csv",
    "geo": "olist_geolocation_dataset.csv",
    "translation": "product_category_name_translation.csv",
}


def transform(raw):
    tables = {name: frame.copy() for name, frame in raw.items()}
    audit = []

    def log(step, count):
        audit.append({"check": step, "rows": int(count)})

    def numeric(frame, columns):
        for col in columns:
            source = frame[col]
            frame[col] = pd.to_numeric(source, errors="coerce").astype(float)
            log(
                f"invalid_numeric:{col}",
                (source.notna() & frame[col].isna()).sum(),
            )

    o, i, p = tables["orders"], tables["items"], tables["products"]
    c, s, g, tr = (
        tables[k] for k in ["customers", "sellers", "geo", "translation"]
    )
    dates = [
        "order_purchase_timestamp",
        "order_approved_at",
        "order_delivered_carrier_date",
        "order_delivered_customer_date",
        "order_estimated_delivery_date",
    ]
    for col in dates:
        source = o[col]
        o[col] = pd.to_datetime(source, errors="coerce", format="mixed")
        log(f"invalid_date:{col}", (source.notna() & o[col].isna()).sum())
    for frame, key in [
        (o, "order_id"),
        (p, "product_id"),
        (c, "customer_id"),
        (s, "seller_id"),
    ]:
        assert (
            frame[key].notna().all() and frame[key].is_unique
        ), f"Khóa lỗi: {key}"
    assert tr.product_category_name.is_unique, "Bảng dịch trùng category"
    numeric(i, ["price", "freight_value"])
    physical = [
        "product_weight_g",
        "product_length_cm",
        "product_height_cm",
        "product_width_cm",
    ]
    numeric(p, physical)
    p["product_weight_g"] = p.product_weight_g.mask(p.product_weight_g.eq(0))
    p["item_physical_score"] = p[physical].prod(axis=1, min_count=4) / 1000
    translations = tr.set_index(
        "product_category_name"
    ).product_category_name_english.to_dict()
    translations.setdefault("pc_gamer", "pc_gamer")
    translations.setdefault(
        "portateis_cozinha_e_preparadores_de_alimentos",
        "portable_kitchen_and_food_preparers",
    )
    category = p.product_category_name.fillna("unknown")
    p["product_category_name"] = category.map(translations).where(
        category.ne("unknown"), "unknown"
    )

    before = len(g)
    g = g.drop_duplicates().copy()
    log("duplicate_geo_removed", before - len(g))
    numeric(g, ["geolocation_lat", "geolocation_lng"])
    g["zip"] = g.geolocation_zip_code_prefix.str.zfill(5)
    inside = g.geolocation_lat.between(-33.8, 5.3) & g.geolocation_lng.between(
        -74, -34.7
    )
    log("geo_outside_bbox_or_missing", (~inside).sum())
    # R18: ZIP không có tọa độ hợp lệ vẫn có thể join, nhưng tọa độ giữ null.
    geo = (
        g.loc[inside]
        .groupby("zip")[["geolocation_lat", "geolocation_lng"]]
        .median()
        .round(6)
    )
    for frame, prefix in [(c, "customer"), (s, "seller")]:
        frame["zip"] = frame[f"{prefix}_zip_code_prefix"].str.zfill(5)
        coords = geo.rename(
            columns={
                "geolocation_lat": f"{prefix}_lat",
                "geolocation_lng": f"{prefix}_lng",
            }
        )
        joined = frame.join(coords, on="zip", validate="many_to_one")
        if prefix == "customer":
            c = joined
        else:
            s = joined

    log("items_missing_price_removed", i.price.isna().sum())
    i = i.loc[i.price.notna()].copy()
    log(
        "orders_missing_purchase_removed",
        o.order_purchase_timestamp.isna().sum(),
    )
    o = o.loc[o.order_purchase_timestamp.notna()].copy()
    delivered, estimated = (
        o.order_delivered_customer_date,
        o.order_estimated_delivery_date,
    )
    purchased, approved, carrier = (
        o.order_purchase_timestamp,
        o.order_approved_at,
        o.order_delivered_carrier_date,
    )
    o["delay_days"] = (
        delivered.dt.normalize() - estimated.dt.normalize()
    ).dt.days
    o["is_late"] = o.delay_days.gt(0).where(
        delivered.notna() & estimated.notna()
    )
    o["has_missing_milestone"] = o.order_status.eq("delivered") & (
        approved.isna() | carrier.isna() | delivered.isna()
    )
    o["has_time_anomaly"] = (
        (carrier < purchased)
        | (carrier < approved)
        | (delivered < carrier)
        | (o.order_status.ne("delivered") & delivered.notna())
    )
    o["shipping_days_estimated"] = (
        (estimated - purchased).dt.total_seconds() / 86400
    ).round(2)
    o.loc[estimated < purchased, "shipping_days_estimated"] = np.nan
    o["order_weekday"] = purchased.dt.dayofweek
    o["order_purchase_month"] = purchased.dt.month

    rows = (
        i.merge(
            o[["order_id", "customer_id"]],
            on="order_id",
            validate="many_to_one",
        )
        .merge(
            p[["product_id", "product_category_name", "item_physical_score"]],
            on="product_id",
            how="left",
            validate="many_to_one",
        )
        .merge(
            s[["seller_id", "seller_lat", "seller_lng"]],
            on="seller_id",
            how="left",
            validate="many_to_one",
        )
        .merge(
            c[["customer_id", "customer_lat", "customer_lng"]],
            on="customer_id",
            how="left",
            validate="many_to_one",
        )
    )
    lat_s, lon_s, lat_c, lon_c = [
        np.radians(rows[col].astype(float))
        for col in ["seller_lat", "seller_lng", "customer_lat", "customer_lng"]
    ]
    a = (
        np.sin((lat_c - lat_s) / 2) ** 2
        + np.cos(lat_s) * np.cos(lat_c) * np.sin((lon_c - lon_s) / 2) ** 2
    )
    rows["distance_km"] = 2 * 6371 * np.arcsin(np.sqrt(a.clip(0, 1)))
    group = rows.groupby("order_id", sort=False)
    features = group.agg(
        freight_value=("freight_value", "sum"),
        distance_km=("distance_km", "max"),
        item_physical_score=("item_physical_score", "sum"),
    )
    for col in features:
        features.loc[group[col].count().lt(group.size()), col] = np.nan
    categories = (
        rows.dropna(subset=["product_category_name"])
        .groupby(["order_id", "product_category_name"])
        .size()
        .rename("n")
        .reset_index()
        .sort_values(
            ["order_id", "n", "product_category_name"],
            ascending=[True, False, True],
        )
        .drop_duplicates("order_id")
        .set_index("order_id")
        .product_category_name
    )
    features["product_category_name"] = categories
    fact = o.merge(features, on="order_id", how="left", validate="one_to_one")
    labeled = fact.loc[fact.is_late.notna()].copy()
    log("warehouse_orders", len(fact))
    log("unlabeled_orders_excluded_from_ML", len(fact) - len(labeled))
    static = [
        "distance_km",
        "freight_value",
        "shipping_days_estimated",
        "order_weekday",
        "order_purchase_month",
        "product_category_name",
        "item_physical_score",
    ]
    data = labeled.dropna(subset=static).reset_index(drop=True)
    log("labeled_missing_static_features_excluded", len(labeled) - len(data))
    log("retained_time_anomaly", data.has_time_anomaly.sum())
    log("retained_missing_milestone", data.has_missing_milestone.sum())
    data["is_late"] = data.is_late.astype(int)
    links = rows[["order_id", "seller_id"]].drop_duplicates()
    assert links.seller_id.notna().all(), "Seller bị thiếu"
    assert data.order_id.is_unique
    assert np.isfinite(
        data[[x for x in static if x != "product_category_name"]].to_numpy(
            float
        )
    ).all()
    return data, links, pd.DataFrame(audit)


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


def load_orders(data_dir):
    """Read the same raw CSVs and ETL rules as the standalone notebook."""
    data_dir = Path(data_dir)
    missing = [
        name for name in FILES.values() if not (data_dir / name).is_file()
    ]
    if missing:
        raise FileNotFoundError(f"Missing CSVs in {data_dir}: {missing}")
    raw = {
        key: pd.read_csv(data_dir / name, dtype="string", encoding="utf-8-sig")
        for key, name in FILES.items()
    }
    data, links, _ = transform(raw)
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


def train(data_dir, output_dir):
    """Select on validation, then refit and evaluate one common outer fold."""
    output = Path(output_dir)
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(
            "Use an empty output directory for this training run"
        )
    data, links = load_orders(data_dir)
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
    parser.add_argument("--data-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    train(args.data_dir, args.output_dir)
