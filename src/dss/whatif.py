"""Rank orders for intervention by calibrated expected net benefit."""

import argparse
import json
from itertools import product
from numbers import Integral
from pathlib import Path

import joblib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sqlalchemy import text

from src.common.db import get_engine
from src.ml.late_risk import MODEL_NAMES, load_orders, predict_late
from src.ml.late_risk import seller_history

UNKNOWN = "Chưa phân nhóm"
REVIEW_QUERY = """
WITH per_order AS (
    SELECT order_id, avg(review_score) AS stars,
           avg(CASE WHEN review_score <= 2 THEN 1.0 ELSE 0.0 END) AS bad_rate
    FROM dw.fact_review
    WHERE review_score BETWEEN 1 AND 5
    GROUP BY order_id
)
SELECT f.is_late, count(*) AS reviewed_orders,
       avg(r.stars) AS mean_stars, avg(r.bad_rate) AS low_review_rate
FROM per_order r
JOIN dw.fact_order_fulfillment f ON f.order_id = r.order_id
WHERE f.is_late IS NOT NULL
GROUP BY f.is_late ORDER BY f.is_late
"""


def score_orders(model_dir, orders, segments, factors):
    """Score once per model, before evaluating any intervention scenarios."""
    metadata = orders[["order_id", "customer_unique_id"]].merge(
        segments[["customer_unique_id", "kmeans_segment"]],
        how="left",
        on="customer_unique_id",
        validate="many_to_one",
    )
    if (
        segments.customer_unique_id.isna().any()
        or segments.kmeans_segment.isna().any()
    ):
        raise ValueError("Missing customer or segment in K-Means file")
    metadata["kmeans_segment"] = metadata.kmeans_segment.fillna(UNKNOWN)
    if not isinstance(factors, dict) or any(
        not isinstance(v, (float, int))
        or isinstance(v, bool)
        or not np.isfinite(v)
        or v < 0
        for v in factors.values()
    ):
        raise ValueError("Segment factors must be finite nonnegative numbers")
    metadata["factor"] = metadata.kmeans_segment.map({**factors, UNKNOWN: 1})
    if metadata.factor.isna().any():
        raise ValueError("Provide a factor for each matched customer segment")
    frames = []
    for name in MODEL_NAMES:
        bundle = joblib.load(Path(model_dir) / f"{name}.joblib")
        scores = predict_late(bundle, orders)[["order_id", "p_late"]]
        frames.append(
            metadata.merge(scores, validate="one_to_one").assign(model=name)
        )
    return pd.concat(frames, ignore_index=True)


def evaluate(scores, loss, cost, efficacy, capacity=None):
    """Rank candidates for one decision day, separately for each model."""
    if not np.isfinite([loss, cost, efficacy]).all() or min(loss, cost) < 0:
        raise ValueError("Loss and cost must be finite and nonnegative")
    if not 0 <= efficacy <= 1:
        raise ValueError("Efficacy must be in [0, 1]")
    if capacity is not None and (
        isinstance(capacity, bool)
        or not isinstance(capacity, Integral)
        or capacity < 0
    ):
        raise ValueError("Capacity must be a nonnegative integer or unlimited")
    data = scores.assign(
        base_loss=loss, cost=cost, efficacy=efficacy, capacity=capacity
    )
    data["loss_if_late"] = loss * data.factor
    data["avoided_late"] = data.p_late * efficacy
    data["gross"] = data.avoided_late * data.loss_if_late
    data["net"] = data.gross - cost
    data = data.sort_values(
        ["model", "net", "p_late", "order_id"],
        ascending=[True, False, False, True],
    )
    data["rank"] = data.groupby("model").cumcount() + 1
    data["selected"] = data.net.gt(0)
    if capacity is not None:
        data["selected"] &= data["rank"].le(capacity)
    return data


def summarize(data):
    keys = ["model", "base_loss", "cost", "efficacy", "capacity"]
    totals = data[keys + ["selected"]].copy()
    for col in ["avoided_late", "gross", "net"]:
        totals[col] = data[col].where(data.selected, 0)
    totals["total_cost"] = data.cost.where(data.selected, 0)
    return totals.groupby(keys, dropna=False, as_index=False).sum()


def by_group(data, links, column):
    pairs = links[["order_id", column]].drop_duplicates()
    weights = pairs.groupby("order_id")[column].transform("size")
    pairs = pairs.assign(orders=1 / weights)
    rows = data.merge(pairs, on="order_id", how="left")
    if rows[column].isna().any():
        raise ValueError(f"Missing {column} for an order")
    rows["expected_late"] = rows.p_late * rows.orders
    rows["selected_net"] = rows.net.where(rows.selected, 0) * rows.orders
    keys = ["model", "base_loss", "cost", "efficacy", "capacity", column]
    return rows.groupby(keys, dropna=False, as_index=False)[
        ["orders", "expected_late", "selected_net"]
    ].sum()


def sensitivity(scores, loss, cost, efficacy, capacity):
    base = dict(loss=loss, cost=cost, efficacy=efficacy, capacity=capacity)
    baseline = summarize(evaluate(scores, **base)).set_index("model").net
    frames = []
    for parameter in ("loss", "cost", "efficacy"):
        for change in (0.8, 1.2):
            value = base[parameter] * change
            if parameter == "efficacy":
                value = min(value, 1)
            params = {**base, parameter: value}
            result = summarize(evaluate(scores, **params))
            result["delta_net"] = result.net - result.model.map(baseline)
            frames.append(
                result.assign(parameter=parameter, value=value, change=change)
            )
    return pd.concat(frames, ignore_index=True)


def plot_tornado(table, path):
    names = table.model.unique()
    fig, axes = plt.subplots(
        len(names), 1, figsize=(8, 8), layout="constrained"
    )
    axes = np.atleast_1d(axes)
    for name, ax in zip(names, axes):
        values = table.loc[table.model.eq(name)].pivot(
            index="parameter",
            columns="change",
            values="delta_net",
        )
        values = values.loc[
            values.max(axis=1).sub(values.min(axis=1)).sort_values().index
        ]
        y = np.arange(len(values))
        for change, offset, label in [
            (0.8, -0.18, "-20%"),
            (1.2, 0.18, "+20%"),
        ]:
            ax.barh(y + offset, values[change], height=0.35, label=label)
        ax.set_yticks(y, values.index)
        ax.axvline(0, color="black", linewidth=0.6)
        ax.set_title(name)
    axes[0].legend()
    axes[-1].set_xlabel("Change in expected net benefit")
    fig.savefig(path, dpi=160)
    plt.close(fig)


def run_whatif(scores, links, loss, costs, efficacies, capacities):
    scenarios = list(
        product(
            dict.fromkeys(costs),
            dict.fromkeys(efficacies),
            dict.fromkeys(capacities),
        )
    )
    if not scenarios:
        raise ValueError("Provide at least one scenario")
    data = pd.concat(
        [evaluate(scores, loss, *s) for s in scenarios], ignore_index=True
    )
    routes = links.assign(
        route=links.seller_state.fillna("?").astype(str)
        + " -> "
        + links.customer_state.fillna("?").astype(str)
    )
    return {
        "orders": data,
        "summary": summarize(data),
        "sellers": by_group(data, links, "seller_id"),
        "routes": by_group(data, routes, "route"),
        "sensitivity": sensitivity(scores, loss, *scenarios[0]),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-dir", required=True, type=Path)
    parser.add_argument(
        "--day", required=True, help="Purchase date (YYYY-MM-DD)"
    )
    parser.add_argument("--segments", required=True, type=Path)
    parser.add_argument(
        "--factors",
        required=True,
        type=Path,
        help="JSON mapping segment to loss factor",
    )
    parser.add_argument("--loss", type=float, required=True)
    parser.add_argument("--cost", type=float, nargs="+", required=True)
    parser.add_argument("--efficacy", type=float, nargs="+", required=True)
    parser.add_argument("--capacity", nargs="+", default=["all"])
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    capacities = [None if c == "all" else int(c) for c in args.capacity]
    engine = get_engine()
    try:
        with engine.connect().execution_options(
            isolation_level="REPEATABLE READ"
        ) as conn:
            orders, links = load_orders(conn, decision_day=args.day)
            reviews = pd.read_sql_query(text(REVIEW_QUERY), conn)
    finally:
        engine.dispose()
    history = joblib.load(args.model_dir / "seller_history.joblib")
    pairs = pd.concat([history["links"], links])[
        ["order_id", "seller_id"]
    ].drop_duplicates()
    orders = seller_history(orders, history["train"], pairs)
    scores = score_orders(
        args.model_dir,
        orders,
        pd.read_csv(args.segments, dtype="string"),
        json.loads(args.factors.read_text(encoding="utf-8-sig")),
    )
    results = run_whatif(
        scores, links, args.loss, args.cost, args.efficacy, capacities
    )
    results["review_stats"] = reviews
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for name, table in results.items():
        table.to_csv(args.output_dir / f"{name}.csv", index=False)
        print(name, table.head(20).to_string(index=False), sep="\n")
    plot_tornado(results["sensitivity"], args.output_dir / "tornado.png")


if __name__ == "__main__":
    main()
