"""Compare late risk before and after changing delivery promises."""

import argparse
from numbers import Integral
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from src.ml.late_risk import MODEL_NAMES, predict_late, prepare_orders


def load_models(model_dir):
    model_dir = Path(model_dir)
    models = {}
    for name in MODEL_NAMES:
        bundle = joblib.load(model_dir / f"{name}.joblib")
        if not np.array_equal(bundle["model"].classes_, [0, 1]):
            raise ValueError(f"Invalid class labels: {name}")
        if not 0 <= bundle["threshold"] <= 1:
            raise ValueError(f"Invalid threshold: {name}")
        models[name] = bundle
    if len({(b["fold"], b["seed"]) for b in models.values()}) != 1:
        raise ValueError(
            "All three models must come from the same fold and seed"
        )
    return models


def build_scenario(orders, estimated_days=0):
    if isinstance(estimated_days, bool) or not isinstance(
        estimated_days, Integral
    ):
        raise ValueError("estimated_days must be an integer")
    data = prepare_orders(orders)
    data["order_estimated_delivery_date"] += pd.Timedelta(
        days=int(estimated_days)
    )
    data["shipping_days_estimated"] = (
        (
            data.order_estimated_delivery_date - data.order_purchase_timestamp
        ).dt.total_seconds()
        / 86400
    ).round(2)
    return prepare_orders(data)


def run_whatif(model_dir, orders, estimated_days=0):
    """Return baseline and scenario predictions for all three models."""
    models = load_models(model_dir)
    before = prepare_orders(orders)
    after = build_scenario(before, estimated_days)
    results = []
    for name, bundle in models.items():
        baseline = predict_late(bundle, before)
        for scenario, data in (("before", before), ("after", after)):
            predicted = (
                baseline.copy()
                if scenario == "before"
                else predict_late(bundle, data)
            )
            predicted["model"] = name
            predicted["scenario"] = scenario
            predicted["estimated_days"] = (
                0 if scenario == "before" else estimated_days
            )
            predicted["estimated_delivery_date"] = (
                data.order_estimated_delivery_date.to_numpy()
            )
            predicted["risk_delta"] = (
                predicted.risk_score - baseline.risk_score
            )
            predicted["baseline_label"] = baseline.predicted_label
            predicted["label"] = predicted.predicted_label.map(
                {0: "On time", 1: "Late"}
            )
            results.append(predicted)
    return pd.concat(results, ignore_index=True)


def summarize(results):
    """Count alerts and label changes for each scenario and model."""
    after = results.loc[results.scenario.eq("after")].copy()
    after["on_time_to_late"] = after.baseline_label.eq(
        0
    ) & after.predicted_label.eq(1)
    after["late_to_on_time"] = after.baseline_label.eq(
        1
    ) & after.predicted_label.eq(0)
    return after.groupby(["model", "estimated_days"], as_index=False).agg(
        orders=("order_id", "size"),
        alerts_before=("baseline_label", "sum"),
        alerts_after=("predicted_label", "sum"),
        on_time_to_late=("on_time_to_late", "sum"),
        late_to_on_time=("late_to_on_time", "sum"),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--orders-file", type=Path, required=True)
    parser.add_argument(
        "--estimated-days", type=int, nargs="+", default=[0, 1, 2, 3]
    )
    args = parser.parse_args()
    orders = pd.read_csv(args.orders_file, dtype={"order_id": "string"})
    results = pd.concat(
        [
            run_whatif(args.model_dir, orders, days)
            for days in dict.fromkeys(args.estimated_days)
        ],
        ignore_index=True,
    )
    print(results.to_string(index=False))
    print("\nSummary:")
    print(summarize(results).to_string(index=False))
