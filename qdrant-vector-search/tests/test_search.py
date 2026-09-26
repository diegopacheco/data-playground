import csv
import json
import os
import unittest
import urllib.parse
import urllib.request
from pathlib import Path

QDRANT_URL = os.environ.get("QDRANT_URL", "http://localhost:26500")
UI_URL = os.environ.get("UI_URL", "http://localhost:26501")
CSV = Path(__file__).resolve().parent.parent / "data" / "products.csv"
ROWS = list(csv.DictReader(CSV.open(newline="")))
BY_ID = {int(r["id"]): r for r in ROWS}


def get(path, **params):
    with urllib.request.urlopen(f"{UI_URL}{path}?{urllib.parse.urlencode(params)}", timeout=60) as r:
        return json.load(r)


def qdrant(path, body):
    request = urllib.request.Request(QDRANT_URL + path, data=json.dumps(body).encode(), method="POST",
                                     headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=30) as r:
        return json.load(r)["result"]


def names(response):
    return [r["name"] for r in response["results"]]


class CollectionTest(unittest.TestCase):
    def test_every_csv_row_is_one_point(self):
        count = qdrant("/collections/products/points/count", {"exact": True})["count"]
        self.assertEqual(count, len(ROWS), "each product must be stored exactly once, no duplicates after reruns")

    def test_payload_matches_csv(self):
        points = qdrant("/collections/products/points", {"ids": list(BY_ID), "with_payload": True})
        self.assertEqual(len(points), len(ROWS))
        for p in points:
            row = BY_ID[p["id"]]
            self.assertEqual(p["payload"]["name"], row["name"])
            self.assertEqual(p["payload"]["category"], row["category"])
            self.assertEqual(p["payload"]["price"], float(row["price"]), "price filters rely on numeric payloads")
            self.assertIs(p["payload"]["in_stock"], row["in_stock"] == "true")

    def test_filtered_fields_are_indexed(self):
        schema = get("/api/info")["payload_schema"]
        self.assertEqual(schema.get("category"), "keyword")
        self.assertEqual(schema.get("price"), "float")
        self.assertEqual(schema.get("in_stock"), "bool")

    def test_category_facets_match_csv(self):
        expected = {}
        for r in ROWS:
            expected[r["category"]] = expected.get(r["category"], 0) + 1
        facets = {c["category"]: c["count"] for c in get("/api/info")["categories"]}
        self.assertEqual(facets, expected)


class SemanticSearchTest(unittest.TestCase):
    EXPECTED_TOP_HIT = {
        "keep my coffee hot on the way to work": "Insulated Travel Mug",
        "block out airplane noise on a long flight": "Wireless Noise Cancelling Headphones",
        "stay warm sleeping outdoors in freezing mountains": "Down Sleeping Bag",
        "film my surfing sessions underwater": "4K Action Camera",
        "how do databases scale across many machines": "Designing Data-Intensive Applications",
        "clean dog hair off the floor automatically": "Robot Vacuum",
    }

    def test_natural_language_question_ranks_the_right_product_first(self):
        for query, expected in self.EXPECTED_TOP_HIT.items():
            with self.subTest(query=query):
                self.assertEqual(names(get("/api/search", q=query, mode="semantic"))[0], expected)

    def test_scores_are_sorted_descending(self):
        scores = [r["score"] for r in get("/api/search", q="gear for a camping trip", mode="semantic")["results"]]
        self.assertEqual(scores, sorted(scores, reverse=True))


class FilterTest(unittest.TestCase):
    def test_category_filter_excludes_the_best_unfiltered_match(self):
        query = "block out airplane noise on a long flight"
        unfiltered = get("/api/search", q=query, mode="semantic")["results"]
        filtered = get("/api/search", q=query, mode="semantic", category="kitchen", limit=50)["results"]
        self.assertEqual(unfiltered[0]["category"], "electronics")
        self.assertTrue(filtered)
        self.assertEqual({r["category"] for r in filtered}, {"kitchen"})
        self.assertNotIn(unfiltered[0]["id"], [r["id"] for r in filtered])

    def test_price_range_returns_exactly_the_matching_rows(self):
        expected = {int(r["id"]) for r in ROWS if r["category"] == "books" and 15 <= float(r["price"]) <= 25}
        results = get("/api/search", q="something to read", mode="semantic", category="books",
                      price_min=15, price_max=25, limit=100)["results"]
        self.assertEqual({r["id"] for r in results}, expected, "a filter is exact, not approximate")

    def test_in_stock_and_rating_filters_drop_non_matching_payloads(self):
        expected = {int(r["id"]) for r in ROWS if r["in_stock"] == "true" and float(r["rating"]) >= 4.6}
        results = get("/api/search", q="anything", mode="semantic", in_stock="true", min_rating=4.6, limit=100)["results"]
        self.assertEqual({r["id"] for r in results}, expected)
        self.assertTrue(all(r["in_stock"] and r["rating"] >= 4.6 for r in results))


class KeywordAndHybridTest(unittest.TestCase):
    def test_keyword_mode_only_returns_documents_with_the_term(self):
        expected = {int(r["id"]) for r in ROWS if r["brand"] == "Nordvik"}
        results = get("/api/search", q="Nordvik", mode="keyword", limit=100)["results"]
        self.assertEqual({r["id"] for r in results}, expected, "bm25 must match the brand token and nothing else")

    def test_semantic_finds_what_keyword_cannot(self):
        self.assertEqual(get("/api/search", q="thermos", mode="keyword")["results"], [], "no document contains the word")
        self.assertEqual(names(get("/api/search", q="thermos", mode="semantic"))[0], "Insulated Travel Mug")

    def test_hybrid_fuses_both_lists_and_ranks_the_item_both_agree_on_first(self):
        query = "Nordvik warm sleeping"
        top = {m: [r["id"] for r in get("/api/search", q=query, mode=m, limit=20)["results"]] for m in ("semantic", "keyword")}
        hybrid = get("/api/search", q=query, mode="hybrid")
        ids = [r["id"] for r in hybrid["results"]]
        self.assertEqual(hybrid["request"]["query"], {"fusion": "rrf"})
        self.assertTrue(set(ids) <= set(top["semantic"]) | set(top["keyword"]))
        self.assertNotEqual(ids, top["semantic"][:len(ids)], "hybrid must differ from pure semantic")
        self.assertNotEqual(ids, top["keyword"][:len(ids)], "hybrid must differ from pure keyword")
        self.assertEqual(top["semantic"][0], top["keyword"][0])
        self.assertEqual(ids[0], top["semantic"][0])
        self.assertEqual(hybrid["results"][0]["name"], "Down Sleeping Bag")


class RecommendTest(unittest.TestCase):
    def test_more_like_a_tent_is_outdoor_gear_and_not_the_tent_itself(self):
        results = get("/api/recommend", id=15, limit=5)["results"]
        ids = [r["id"] for r in results]
        self.assertNotIn(15, ids)
        self.assertGreaterEqual(sum(r["category"] == "outdoor" for r in results[:3]), 2)

    def test_recommend_respects_filters(self):
        results = get("/api/recommend", id=15, category="apparel", limit=50)["results"]
        self.assertTrue(results)
        self.assertEqual({r["category"] for r in results}, {"apparel"})


if __name__ == "__main__":
    unittest.main()
