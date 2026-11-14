"""Kiểm tra RFM và phân cụm bằng dữ liệu tổng hợp, không cần database thật."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from sqlalchemy import create_engine
from streamlit.testing.v1 import AppTest

import numpy as np
import pandas as pd

from src.ml.kmean import build_rfm, name_clusters, run_kmeans
from src.ml.kmean import load_orders, validate_orders


def make_orders():
    return pd.DataFrame({
        "order_id": ["a", "b", "c", "d", "e"],
        "customer_unique_id": ["u1", "u1", "u2", "u3", "u4"],
        "order_purchase_timestamp": pd.to_datetime([
            "2018-01-01", "2018-01-03", "2018-02-01",
            "2018-03-01", "2018-04-01",
        ]),
        "order_revenue": [100.0, 200.0, 50.0, 400.0, 900.0],
    })


class KmeansTests(unittest.TestCase):
    def test_query_includes_both_years_without_sampling(self):
        engine = create_engine("sqlite://")
        try:
            with engine.begin() as conn:
                conn.exec_driver_sql("ATTACH DATABASE ':memory:' AS dw")
                conn.exec_driver_sql(
                    "CREATE TABLE dw.dim_customer "
                    "(customer_key INTEGER, customer_unique_id TEXT)"
                )
                conn.exec_driver_sql(
                    "INSERT INTO dw.dim_customer VALUES (1, 'customer')"
                )
                conn.exec_driver_sql(
                    "CREATE TABLE dw.dim_order_status "
                    "(order_status_key INTEGER, order_status TEXT)"
                )
                conn.exec_driver_sql(
                    "INSERT INTO dw.dim_order_status VALUES (1, 'delivered')"
                )
                conn.exec_driver_sql(
                    "CREATE TABLE dw.fact_order_fulfillment "
                    "(order_id TEXT, customer_key INTEGER, "
                    "order_status_key INTEGER, "
                    "order_purchase_timestamp TEXT, order_revenue REAL)"
                )
                rows = [
                    ("before", 1, 1, "2016-12-31 23:59:59", 100),
                    ("start", 1, 1, "2017-01-01 00:00:00", 100),
                    ("end", 1, 1, "2018-12-31 23:59:59", 100),
                    ("after", 1, 1, "2019-01-01 00:00:00", 100),
                ]
                conn.exec_driver_sql(
                    "INSERT INTO dw.fact_order_fulfillment "
                    "VALUES (?, ?, ?, ?, ?)", rows,
                )
            orders = load_orders(engine, 2017, 2018)
            self.assertEqual(set(orders["order_id"]), {"start", "end"})
            for start, end in [(2018, 2017), (0, 2018), (2017, 9999)]:
                with self.assertRaises(ValueError):
                    load_orders(engine, start, end)
        finally:
            engine.dispose()

    @patch("src.common.db.get_engine")
    @patch("src.ml.kmean.run_kmeans")
    def test_dashboard_passes_selected_years(self, train, get_engine):
        get_engine.return_value = Mock()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "segments.csv"
            pd.DataFrame({
                "customer_unique_id": ["001"],
                "kmeans_segment": ["Khách mua lại"],
            }).to_csv(path, index=False)
            train.return_value = path
            root = Path(__file__).resolve().parents[1]
            app = AppTest.from_file(
                str(root / "src/app/pages/5_Mo_hinh_ML.py")
            )
            app.run()
            train.assert_not_called()
            app.number_input[0].set_value(2016)
            app.number_input[1].set_value(2018)
            app.button[0].click().run()
            self.assertFalse(app.exception)
            train.assert_called_once_with(get_engine.return_value, 2016, 2018)
            self.assertEqual(app.metric[0].value, "1")
            get_engine.return_value.dispose.assert_called_once()
            app.number_input[0].set_value(2019)
            app.button[0].click().run()
            self.assertTrue(app.error)
            self.assertEqual(len(app.metric), 0)
            self.assertEqual(train.call_count, 1)

    def test_rfm_counts_orders_and_excludes_zero_revenue(self):
        orders = make_orders()
        orders.loc[4, "order_revenue"] = 0
        rfm = build_rfm(validate_orders(orders))
        self.assertNotIn("u4", rfm.index)
        self.assertEqual(rfm.loc["u1", "frequency"], 2)
        self.assertEqual(rfm.loc["u1", "monetary"], 300)
        self.assertEqual(rfm.loc["u1", "avg_order_value"], 150)
        self.assertEqual(rfm.loc["u3", "recency_days"], 1)

    def test_invalid_orders_are_rejected(self):
        for value in [-1, np.inf, np.nan]:
            with self.subTest(revenue=value):
                orders = make_orders()
                orders.loc[0, "order_revenue"] = value
                with self.assertRaises(ValueError):
                    validate_orders(orders)
        orders = make_orders()
        with self.assertRaises(ValueError):
            validate_orders(pd.concat([orders, orders.iloc[:1]]))

    def test_labels_match_four_cluster_reference(self):
        profile = pd.DataFrame({
            "kmeans_cluster": [0, 1, 2, 3],
            "recency_days": [180, 470, 200, 180],
            "frequency": [1, 1, 2, 1],
            "monetary": [45, 85, 182, 150],
        })
        expected = [
            "Khách chi tiêu thấp", "Khách lâu chưa mua",
            "Khách mua lại", "Khách chi tiêu cao",
        ]
        self.assertEqual(name_clusters(profile).tolist(), expected)
        profile["kmeans_cluster"] = [3, 2, 1, 0]
        self.assertEqual(name_clusters(profile).tolist(), expected[::-1])
        profile["frequency"] = 1
        labels = name_clusters(profile)
        self.assertNotIn("Khách mua lại", labels.values)
        self.assertEqual(labels.nunique(), 4)

    @patch("src.ml.kmean.load_orders")
    def test_run_writes_four_clusters_and_replaces_old_csv(self, load):
        load.return_value = make_orders()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "segments.csv"
            path.write_text("old result", encoding="utf-8")
            saved = run_kmeans(None, 2017, 2018, path)
            self.assertEqual(saved, path.resolve())
            result = pd.read_csv(path)
            self.assertEqual(len(result), 4)
            self.assertEqual(result["kmeans_cluster"].nunique(), 4)
            self.assertEqual(result["kmeans_segment"].nunique(), 4)

    @patch("src.ml.kmean.load_orders")
    def test_too_few_distinct_profiles_preserves_output(self, load):
        orders = make_orders()
        orders["order_purchase_timestamp"] = pd.Timestamp("2018-01-01")
        orders["order_revenue"] = 100
        orders["customer_unique_id"] = orders["order_id"]
        load.return_value = orders
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "segments.csv"
            path.write_text("old result", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "4 hồ sơ"):
                run_kmeans(None, 2017, 2018, path)
            self.assertEqual(path.read_text(encoding="utf-8"), "old result")


if __name__ == "__main__":
    unittest.main()
