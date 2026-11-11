"""So sánh review dự kiến khi thay đổi ngày hẹn và ngày giao thực tế."""

from numbers import Integral
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from src.ml.review_quality import REVIEW_LABELS
from src.ml.review_quality import build_features
from src.ml.review_quality import clean_orders
from src.ml.review_quality import predict_review


MODEL_NAMES = [
    "logistic_regression",
    "random_forest",
    "gradient_boosting",
]

ORDER_COLUMNS = [
    "order_id",
    "order_purchase_timestamp",
    "order_approved_at",
    "order_delivered_customer_date",
    "order_estimated_delivery_date",
    "item_count",
    "order_revenue",
    "order_freight",
]


def load_models(model_dir):
    """Nạp đủ ba model từ cùng một thư mục kết quả huấn luyện."""
    model_dir = Path(model_dir).resolve()
    paths = {name: model_dir / f"{name}.joblib" for name in MODEL_NAMES}
    missing = [path.name for path in paths.values() if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"Thiếu model trong {model_dir}: {', '.join(missing)}")

    models = {name: joblib.load(path) for name, path in paths.items()}
    for name, model in models.items():
        if not np.array_equal(model.classes_, list(REVIEW_LABELS)):
            raise ValueError(f"Model {name} phải dùng nhãn 0 (review xấu) và 1 (review tốt)")

    return models


def prepare_orders(orders):
    """Kiểm tra đầu vào mà không âm thầm loại đơn khỏi kịch bản."""
    if not orders.columns.is_unique:
        raise ValueError("Tên cột của đơn hàng không được trùng")

    missing = sorted(set(ORDER_COLUMNS) - set(orders.columns))
    if missing:
        raise ValueError(f"Thiếu cột đơn hàng: {', '.join(missing)}")
    if orders.empty:
        raise ValueError("Cần ít nhất một đơn để mô phỏng")

    data = orders[ORDER_COLUMNS].copy()
    data["order_id"] = data["order_id"].astype("string").str.strip().replace(
        "",
        pd.NA,
    )
    cleaned = clean_orders(data)
    if len(cleaned) != len(data):
        raise ValueError("Đơn bị trùng, thiếu dữ liệu hoặc có thời gian, số tiền không hợp lệ")

    return cleaned


def build_scenario(orders, estimated_days=0, delivery_days=0):
    """Dịch ngày theo lịch rồi tính lại các feature như lúc huấn luyện."""
    for days in (estimated_days, delivery_days):
        if isinstance(days, bool) or not isinstance(days, Integral):
            raise ValueError("Số ngày thay đổi phải là số nguyên")

    scenario = prepare_orders(orders)
    scenario["order_estimated_delivery_date"] += pd.Timedelta(days=int(estimated_days))
    scenario["order_delivered_customer_date"] += pd.Timedelta(days=int(delivery_days))

    return build_features(prepare_orders(scenario))


def run_whatif(model_dir, orders, estimated_days=0, delivery_days=0):
    """Gọi ba model trên cùng đơn trước và sau thay đổi ngày giao."""
    models = load_models(model_dir)
    scenarios = {
        "before": build_scenario(orders),
        "after": build_scenario(
            orders,
            estimated_days=estimated_days,
            delivery_days=delivery_days,
        ),
    }
    results = []

    for name, model in models.items():
        for scenario, data in scenarios.items():
            predictions = predict_review(
                model,
                data,
            )
            predictions["estimated_delivery_date"] = data["order_estimated_delivery_date"]
            results.append(predictions.assign(
                model=name,
                scenario=scenario,
            ))

    return pd.concat(
        results,
        ignore_index=True,
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--model-dir",
        required=True,
        help="Thư mục một lần train chứa đủ ba file .joblib",
    )
    parser.add_argument(
        "--orders-file",
        required=True,
        help="CSV đơn hàng với tám cột trong ORDER_COLUMNS",
    )
    parser.add_argument(
        "--estimated-days",
        type=int,
        default=0,
        help="Số ngày lịch cộng vào ngày hẹn; số âm là hẹn sớm hơn",
    )
    parser.add_argument(
        "--delivery-days",
        type=int,
        default=0,
        help="Số ngày lịch cộng vào ngày giao thực tế giả định",
    )
    args = parser.parse_args()
    orders = pd.read_csv(
        args.orders_file,
        dtype={"order_id": "string"},
    )
    result = run_whatif(
        args.model_dir,
        orders,
        estimated_days=args.estimated_days,
        delivery_days=args.delivery_days,
    )
    print(result.to_string(index=False))
