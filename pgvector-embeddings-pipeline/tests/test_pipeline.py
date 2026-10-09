import csv
import json
import os
import sys
import unittest
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))

import db
from embed import embed_query, to_pg

API = f"http://localhost:{os.environ.get('UI_PORT', '24801')}/api"


def get(path, **params):
    with urlopen(f"{API}/{path}?{urlencode(params)}") as r:
        return json.load(r)


def csv_products():
    with (ROOT / "data" / "orders.csv").open() as f:
        rows = list(csv.DictReader(f))
    revenue = {}
    for r in rows:
        revenue[r["product"]] = revenue.get(r["product"], 0.0) + int(r["quantity"]) * float(r["price"])
    return revenue


def parse(vector_text):
    return np.array([float(x) for x in vector_text.strip("[]").split(",")], dtype=np.float64)


class CatalogTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.conn = db.connect()
        cls.expected = csv_products()

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()

    def test_every_product_from_orders_has_exactly_one_embedding(self):
        n, embedded, dims = self.conn.execute(
            "SELECT count(*), count(embedding), min(vector_dims(embedding)) FROM products").fetchone()
        self.assertEqual(n, len(self.expected))
        self.assertEqual(embedded, len(self.expected))
        self.assertEqual(dims, 384)
        self.assertEqual(get("pipeline")["embedded_products"], len(self.expected))

    def test_catalog_revenue_matches_orders_csv(self):
        for name, revenue in self.conn.execute("SELECT name, revenue FROM products").fetchall():
            self.assertAlmostEqual(float(revenue), round(self.expected[name], 2), places=2, msg=name)

    def test_long_descriptions_were_chunked_and_pooled_to_unit_vectors(self):
        chunks, norms = self.conn.execute(
            "SELECT sum(chunks), array_agg(embedding::text) FROM products").fetchone()
        self.assertGreater(chunks, len(self.expected))
        for v in norms:
            self.assertAlmostEqual(float(np.linalg.norm(parse(v))), 1.0, places=4)

    def test_variants_are_every_product_times_600_skus(self):
        n = self.conn.execute("SELECT count(*) FROM variants").fetchone()[0]
        self.assertEqual(n, len(self.expected) * 600)
        self.assertEqual(get("pipeline")["variants"], n)

    def test_hnsw_cosine_indexes_exist_and_planner_uses_them(self):
        defs = dict(self.conn.execute(
            "SELECT indexname, indexdef FROM pg_indexes WHERE indexname LIKE '%hnsw'").fetchall())
        self.assertIn("vector_cosine_ops", defs["products_embedding_hnsw"])
        self.assertIn("vector_cosine_ops", defs["variants_embedding_hnsw"])
        q = to_pg(embed_query("gear for running"))
        plan = json.dumps(self.conn.execute(
            "EXPLAIN (FORMAT JSON) SELECT id FROM variants ORDER BY embedding <=> %s::vector LIMIT 10", (q,)).fetchone()[0])
        self.assertIn("variants_embedding_hnsw", plan)

    def test_postgres_exact_scan_matches_numpy_brute_force(self):
        ids, texts = zip(*self.conn.execute("SELECT id, embedding::text FROM variants ORDER BY id").fetchall())
        matrix = np.stack([parse(t) for t in texts])
        matrix /= np.linalg.norm(matrix, axis=1, keepdims=True)
        for text in ["gear for running", "something to read", "kitchen tools for cooking dinner"]:
            vector = embed_query(text)
            numpy_top = {ids[i] for i in np.argsort(-(matrix @ (vector / np.linalg.norm(vector))))[:10]}
            with self.conn.transaction():
                self.conn.execute("SET LOCAL enable_indexscan = off")
                pg_top = {r[0] for r in self.conn.execute(
                    "SELECT id FROM variants ORDER BY embedding <=> %s::vector LIMIT 10", (to_pg(vector),)).fetchall()}
            self.assertGreaterEqual(len(numpy_top & pg_top), 9, text)

    def test_recall_numbers_were_computed_and_tuned_index_is_near_exact(self):
        modes = get("pipeline")["bench"]["modes"]
        exact = [m for m in modes if m["mode"] == "exact scan"][0]
        self.assertEqual(exact["recall"], 1.0)
        self.assertIn("Seq Scan", exact["plan"])
        hnsw = [m for m in modes if m["mode"] == "hnsw"]
        self.assertEqual(len(hnsw), 8)
        for m in hnsw:
            self.assertTrue(0.0 <= m["recall"] <= 1.0)
            self.assertAlmostEqual(m["recall"], sum(m["per_query_recall"]) / len(m["per_query_recall"]), places=3)
            self.assertIn("Index Scan using variants_embedding_hnsw", m["plan"])
            self.assertLess(m["avg_ms"], exact["avg_ms"])
        by = {(m["index"], m["ef_search"]): m["recall"] for m in hnsw}
        self.assertGreaterEqual(by[("hnsw m=32 ef_construction=200", 100)], 0.95)

    def test_books_query_returns_books_in_top3(self):
        top = get("search", q="something to read", k=3)["results"]
        self.assertEqual([h["category"] for h in top], ["books"] * 3)

    def test_running_query_finds_running_gear(self):
        top = get("search", q="gear for running", k=3)["results"]
        self.assertEqual(top[0]["name"], "Running Jacket")
        self.assertTrue(all(0 < h["score"] <= 1 for h in top))
        self.assertEqual([h["score"] for h in top], sorted([h["score"] for h in top], reverse=True))

    def test_category_filter_restricts_results(self):
        top = get("search", q="something to read", category="sports", k=5)["results"]
        self.assertEqual({h["category"] for h in top}, {"sports"})

    def test_hybrid_uses_full_text_for_author_names(self):
        top = get("search", q="Kleppmann", mode="hybrid", k=3)["results"]
        self.assertEqual(top[0]["name"], "Designing Data-Intensive Applications")
        self.assertIsNotNone(top[0]["rank"])
        books = get("search", q="book about history of humans", mode="hybrid", category="books", k=3)["results"]
        self.assertEqual(books[0]["name"], "Sapiens")
        self.assertEqual({h["category"] for h in books}, {"books"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
