"""Dự đoán review tốt hoặc xấu tại lúc giao hàng và lưu riêng ba model."""

import json
import logging
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import make_column_transformer
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score
from sklearn.metrics import classification_report
from sklearn.metrics import f1_score
from sklearn.metrics import precision_score
from sklearn.metrics import recall_score
from sklearn.metrics import roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder
from sklearn.preprocessing import StandardScaler
from sklearn.utils.class_weight import compute_sample_weight


logger = logging.getLogger(__name__)

REVIEW_LABELS = {
    0: "bad",
    1: "good",
}

VALID_REVIEW_SCORES = [
    1,
    2,
    3,
    4,
    5,
]

FEATURES = [
    "estimated_workdays",
    "actual_workdays",
    "delivery_workday_delta",
    "is_late",
    "average_product_value",
    "total_order_value",
    "freight_ratio",
    "purchase_weekday",
]

DATE_COLUMNS = [
    "order_purchase_timestamp",
    "order_approved_at",
    "order_delivered_customer_date",
    "order_estimated_delivery_date",
]

MONEY_COLUMNS = [
    "item_count",
    "order_revenue",
    "order_freight",
]

ORDERS_QUERY = """
    SELECT DISTINCT
        orders.order_id,
        orders.order_purchase_timestamp,
        source.order_approved_at,
        source.order_delivered_customer_date,
        source.order_estimated_delivery_date,
        orders.item_count,
        orders.order_revenue,
        orders.order_freight
    FROM dw.fact_order_fulfillment AS orders
    JOIN dw.dim_order_status AS statuses
        ON statuses.order_status_key = orders.order_status_key
    JOIN staging.orders AS source ON source.order_id = orders.order_id
    WHERE statuses.order_status = 'delivered'
"""

REVIEWS_QUERY = """
    SELECT DISTINCT
        reviews.order_id,
        reviews.review_id,
        reviews.review_score,
        source.review_answer_timestamp
    FROM dw.fact_review AS reviews
    JOIN staging.order_reviews AS source
        ON source.order_id = reviews.order_id AND source.review_id = reviews.review_id
"""


def load_data(connection):
    """Đọc đơn, review và chuẩn hóa ID từ DW/staging."""
    orders = pd.read_sql_query(
        ORDERS_QUERY,
        connection,
    )
    reviews = pd.read_sql_query(
        REVIEWS_QUERY,
        connection,
    )

    for table in (orders, reviews):
        table["order_id"] = table["order_id"].astype("string").str.strip().replace(
            "",
            pd.NA,
        )

    reviews["review_id"] = reviews["review_id"].astype("string").str.strip().replace(
        "",
        pd.NA,
    )
    return orders, reviews


def clean_orders(orders):
    """Chuyển kiểu và giữ những đơn có thời gian, tiền hàng hợp lệ."""
    for column in DATE_COLUMNS:
        orders[column] = pd.to_datetime(
            orders[column],
            errors="coerce",
            format="mixed",
        )

    for column in MONEY_COLUMNS:
        orders[column] = pd.to_numeric(
            orders[column],
            errors="coerce",
        ).astype(float)

    orders = orders.dropna(
        subset=[
            "order_id",
            *DATE_COLUMNS,
        ],
    ).drop_duplicates()

    if orders["order_id"].duplicated().any():
        raise ValueError("Một order có nhiều bản ghi khác nhau trong DW/staging")

    approved_after_purchase = orders["order_approved_at"] >= orders["order_purchase_timestamp"]
    delivered_after_approval = (
        orders["order_delivered_customer_date"] >= orders["order_approved_at"]
    )
    estimated_after_approval = (
        orders["order_estimated_delivery_date"].dt.normalize()
        >= orders["order_approved_at"].dt.normalize()
    )
    finite_amounts = np.isfinite(orders[MONEY_COLUMNS]).all(axis=1)
    valid_item_count = orders["item_count"].gt(0) & orders["item_count"].mod(1).eq(0)
    valid_amounts = orders["order_revenue"].gt(0) & orders["order_freight"].ge(0)

    valid_orders = (
        approved_after_purchase
        & delivered_after_approval
        & estimated_after_approval
        & finite_amounts
        & valid_item_count
        & valid_amounts
    )
    return orders.loc[valid_orders].copy()


def build_features(orders):
    """Tạo tám đặc trưng tại lúc giao hàng."""
    orders["prediction_at"] = orders["order_delivered_customer_date"]

    workday_columns = {
        "estimated_workdays": "order_estimated_delivery_date",
        "actual_workdays": "order_delivered_customer_date",
    }
    # shortcut: chưa trừ ngày lễ Brazil như notebook, bổ sung khi đổi lịch vận hành.
    for feature, end in workday_columns.items():
        orders[feature] = np.busday_count(
            orders["order_approved_at"].to_numpy().astype("datetime64[D]"),
            orders[end].to_numpy().astype("datetime64[D]"),
        )

    orders["delivery_workday_delta"] = orders["actual_workdays"] - orders["estimated_workdays"]
    delivered_late = (
        orders["order_delivered_customer_date"].dt.normalize()
        > orders["order_estimated_delivery_date"].dt.normalize()
    )
    orders["is_late"] = delivered_late.astype(int)

    orders["average_product_value"] = orders["order_revenue"] / orders["item_count"]
    orders["total_order_value"] = orders["order_revenue"] + orders["order_freight"]
    orders["freight_ratio"] = orders["order_freight"] / orders["total_order_value"]
    orders["purchase_weekday"] = orders["order_purchase_timestamp"].dt.dayofweek
    return orders


def clean_reviews(reviews):
    """Giữ review hợp lệ đầu tiên của mỗi đơn theo thời gian và ID."""
    reviews["review_score"] = pd.to_numeric(
        reviews["review_score"],
        errors="coerce",
    )
    reviews["review_at"] = pd.to_datetime(
        reviews["review_answer_timestamp"],
        errors="coerce",
        format="mixed",
    )
    reviews = reviews.dropna(
        subset=[
            "order_id",
            "review_id",
            "review_at",
        ],
    )
    valid_scores = reviews["review_score"].isin(VALID_REVIEW_SCORES)
    reviews = reviews.loc[valid_scores].drop_duplicates()

    review_key = [
        "order_id",
        "review_at",
        "review_id",
    ]
    if reviews.duplicated(review_key).any():
        raise ValueError("Review cùng ID và thời gian nhưng điểm khác nhau")

    return reviews.sort_values(
        [
            "review_at",
            "review_id",
        ],
    ).drop_duplicates("order_id")


def prepare_data(connection):
    """Giữ đơn có review đầu tiên sau lúc giao và gán nhãn tốt/xấu."""
    orders, reviews = load_data(connection)
    orders = build_features(clean_orders(orders))
    reviews = clean_reviews(reviews)

    review_columns = [
        "order_id",
        "review_at",
        "review_score",
    ]
    data = orders.merge(
        reviews[review_columns],
        on="order_id",
        validate="one_to_one",
    )
    reviewed_after_delivery = data["review_at"] > data["prediction_at"]
    has_binary_label = data["review_score"] != 3
    data = data.loc[reviewed_after_delivery & has_binary_label].copy()
    data["review_label"] = data["review_score"].gt(3).astype(int)

    return data[[
        "order_id",
        "prediction_at",
        "review_at",
        "review_label",
        *FEATURES,
    ]]


def split_data(data):
    """20% đơn mới nhất làm test; train chỉ dùng review đã biết trước mốc test."""
    if len(data) < 2:
        raise ValueError("Không đủ đơn có review để chia train/test")

    ordered = data.sort_values("prediction_at")
    cutoff = ordered["prediction_at"].iloc[int(len(ordered) * 0.8)]
    available_for_training = (
        (ordered["prediction_at"] < cutoff)
        & (ordered["review_at"] < cutoff)
    )
    train = ordered.loc[available_for_training]
    test = ordered.loc[ordered["prediction_at"] >= cutoff]

    if set(train["review_label"]) != set(REVIEW_LABELS):
        raise ValueError("Tập train phải có cả review tốt và review xấu")
    if set(test["review_label"]) != set(REVIEW_LABELS):
        raise ValueError("Tập test phải có cả review tốt và review xấu")

    return train, test, cutoff


def predict_review(model, orders):
    """Trả về nhãn và điểm dự đoán của hai lớp cho mỗi đơn."""
    scores = model.predict_proba(orders[FEATURES])
    predictions = orders[[
        "order_id",
        "prediction_at",
    ]].copy()
    predictions["predicted_label"] = model.classes_[scores.argmax(axis=1)]

    for index, label in enumerate(model.classes_):
        predictions[f"score_{REVIEW_LABELS[label]}_review"] = scores[:, index]

    return predictions


def build_models():
    """Tạo Gradient Boosting và hai model đối chiếu."""
    numeric_features = [name for name in FEATURES if name != "purchase_weekday"]
    linear_features = make_column_transformer(
        (
            StandardScaler(),
            numeric_features,
        ),
        (
            OneHotEncoder(handle_unknown="ignore"),
            [
                "purchase_weekday",
            ],
        ),
    )

    return {
        "logistic_regression": make_pipeline(
            linear_features,
            LogisticRegression(
                class_weight="balanced",
                max_iter=1000,
            ),
        ),
        "random_forest": RandomForestClassifier(
            n_estimators=150,
            max_depth=8,
            min_samples_leaf=20,
            class_weight="balanced",
            random_state=42,
            n_jobs=2,
        ),
        "gradient_boosting": GradientBoostingClassifier(
            max_depth=8,
            min_samples_split=5,
            random_state=42,
        ),
    }


def calculate_metrics(actual, predicted, bad_review_scores):
    """Đo kết quả chung và khả năng nhận diện review xấu."""
    return {
        "accuracy": accuracy_score(
            actual,
            predicted,
        ),
        "macro_f1": f1_score(
            actual,
            predicted,
            labels=list(REVIEW_LABELS),
            average="macro",
            zero_division=0,
        ),
        "bad_review_precision": precision_score(
            actual,
            predicted,
            pos_label=0,
            zero_division=0,
        ),
        "bad_review_recall": recall_score(
            actual,
            predicted,
            pos_label=0,
            zero_division=0,
        ),
        "bad_review_f1": f1_score(
            actual,
            predicted,
            pos_label=0,
            zero_division=0,
        ),
        "roc_auc": roc_auc_score(
            np.asarray(actual) == 0,
            bad_review_scores,
        ),
    }


def train_models(models, train, test, stage):
    """Huấn luyện, đánh giá và lưu riêng từng model."""
    metrics = {}
    reports = {}
    predictions = []
    train_labels = train["review_label"]
    actual = test["review_label"]
    balanced_weights = compute_sample_weight(
        "balanced",
        train_labels,
    )

    for name, model in models.items():
        logger.info(
            "Train %s: %s đơn train, %s đơn test",
            name,
            len(train),
            len(test),
        )
        fit_options = {}
        if name == "gradient_boosting":
            fit_options["sample_weight"] = balanced_weights
        model.fit(
            train[FEATURES],
            train_labels,
            **fit_options,
        )

        predicted = predict_review(
            model,
            test,
        )
        predicted["actual_label"] = actual
        predictions.append(predicted.assign(model=name))

        reports[name] = pd.DataFrame(
            classification_report(
                actual,
                predicted["predicted_label"],
                labels=list(REVIEW_LABELS),
                target_names=list(REVIEW_LABELS.values()),
                output_dict=True,
                zero_division=0,
            ),
        ).T
        metrics[name] = calculate_metrics(
            actual,
            predicted["predicted_label"],
            predicted["score_bad_review"],
        )
        joblib.dump(
            model,
            stage / f"{name}.joblib",
        )

    baseline_label = int(train_labels.mode().iloc[0])
    baseline_name = REVIEW_LABELS[baseline_label]
    metrics[f"always_{baseline_name}"] = calculate_metrics(
        actual,
        np.full(
            len(test),
            baseline_label,
        ),
        np.full(
            len(test),
            float(baseline_label == 0),
        ),
    )
    return metrics, reports, predictions


def save_reports(stage, metrics, reports, predictions):
    """Lưu các bảng đánh giá và trả về bảng tổng hợp."""
    summary = pd.DataFrame.from_dict(
        metrics,
        orient="index",
    ).sort_values(
        "macro_f1",
        ascending=False,
    )
    summary.to_csv(
        stage / "metrics.csv",
        index_label="model",
    )
    pd.concat(
        reports,
        names=[
            "model",
            "label_or_average",
        ],
    ).to_csv(stage / "classification_report.csv")
    pd.concat(
        predictions,
        ignore_index=True,
    ).to_csv(
        stage / "predictions.csv",
        index=False,
    )
    return summary


def save_results(models, train, test, cutoff, output_dir):
    """Chỉ công bố thư mục kết quả sau khi lưu đủ model và báo cáo."""
    root = Path(output_dir).resolve()
    root.mkdir(
        parents=True,
        exist_ok=True,
    )
    destination = root / uuid4().hex

    with TemporaryDirectory(
        prefix=".staging-",
        dir=root,
    ) as temporary:
        stage = Path(temporary)
        metrics, reports, predictions = train_models(
            models,
            train,
            test,
            stage,
        )
        summary = save_reports(
            stage,
            metrics,
            reports,
            predictions,
        )

        metadata = {
            "features": FEATURES,
            "labels": REVIEW_LABELS,
            "excluded_review_score": 3,
            "prediction_time": "delivery",
            "cutoff": cutoff.isoformat(),
            "train_orders": len(train),
            "test_orders": len(test),
            "class_weights": "balanced",
            "models": {name: f"{name}.joblib" for name in models},
        }
        (stage / "run.json").write_text(
            json.dumps(
                metadata,
                indent=2,
            ),
            encoding="utf-8",
        )
        stage.rename(destination)

    return destination, summary


def run_review_quality(connection, output_dir="artifacts/models/review_quality"):
    """Train cùng split, lưu ba model riêng và kết quả đánh giá trong một lần chạy."""
    logger.info("Đọc đơn và review từ DW/staging")
    train, test, cutoff = split_data(prepare_data(connection))
    destination, summary = save_results(
        build_models(),
        train,
        test,
        cutoff,
        output_dir,
    )
    logger.info(
        "Kết quả:\n%s\nĐã lưu model tại %s",
        summary.to_string(),
        destination,
    )
    return destination


if __name__ == "__main__":
    from src.common.db import get_engine

    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s - %(message)s",
    )
    engine = get_engine()
    try:
        run_review_quality(engine)
    finally:
        engine.dispose()
