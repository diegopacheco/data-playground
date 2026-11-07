import glob
import math
import os
import sys
import time
import unittest

import helpers

sys.path.insert(0, os.path.join(helpers.ROOT, "app"))
import embedder

TEST_DOC = os.path.join(helpers.DOCS, "zz-test-volcano.md")
VOLCANO = "Volcano lava flows cool into basalt rock near the crater of the volcano."
GLACIER = "Glacier ice moves slowly down the valley and carves the mountain."
QUERIES = ["how long does shipping to japan take", "reset my password", "refund to my card", "sales tax in brazil"]


def cosine(a, b):
    return sum(x * y for x, y in zip(a, b))


def brute_force(query):
    q = embedder.embed(query)
    scores = {}
    for path in glob.glob(os.path.join(helpers.DOCS, "*.md")):
        with open(path) as handle:
            text = handle.read()
        if text.strip():
            scores[os.path.basename(path)] = cosine(q, embedder.embed(text))
    return scores


def names(result):
    return [r["doc"] for r in result]


class EmbedderTest(unittest.TestCase):
    def test_vectors_are_deterministic_and_unit_length(self):
        a = embedder.embed(VOLCANO)
        self.assertEqual(a, embedder.embed(VOLCANO))
        self.assertAlmostEqual(1.0, math.sqrt(sum(v * v for v in a)), places=9)
        self.assertEqual(embedder.DIMENSIONS, len(a))

    def test_shared_words_score_higher_than_unrelated_text(self):
        q = embedder.embed("lava from the volcano")
        self.assertGreater(cosine(q, embedder.embed(VOLCANO)), cosine(q, embedder.embed(GLACIER)) + 0.3)


class RetrievalTest(unittest.TestCase):
    def setUp(self):
        if os.path.exists(TEST_DOC):
            os.remove(TEST_DOC)
        helpers.wait_for(lambda: helpers.get("docs")["rows"], lambda rows: all(r["doc"] != os.path.basename(TEST_DOC) for r in rows))

    def tearDown(self):
        if os.path.exists(TEST_DOC):
            os.remove(TEST_DOC)

    def assertMatchesBruteForce(self, query, k=3):
        expected = brute_force(query)
        result = helpers.search(query, k)
        top = sorted(expected.values(), reverse=True)[:k]
        self.assertEqual(min(k, len(expected)), len(result))
        for got, want in zip([r["similarity"] for r in result], top):
            self.assertAlmostEqual(want, got, places=5)
        for r in result:
            self.assertAlmostEqual(expected[r["doc"]], r["similarity"], places=5)
        return result

    def search_until(self, query, accept, k=3, seconds=15):
        started = time.time()
        result = helpers.wait_for(lambda: helpers.search(query, k), accept, seconds)
        return result, time.time() - started

    def test_top_k_equals_a_brute_force_cosine_ranking_over_the_folder(self):
        for query in QUERIES:
            with self.subTest(query=query):
                self.assertMatchesBruteForce(query)
        self.assertEqual("shipping.md", helpers.search(QUERIES[0], 1)[0]["doc"])
        self.assertEqual("accounts.md", helpers.search(QUERIES[1], 1)[0]["doc"])

    def test_a_new_doc_becomes_the_top_match_within_seconds(self):
        self.assertNotIn("zz-test-volcano.md", names(helpers.search("volcano lava basalt", 4)))
        helpers.write_atomic(TEST_DOC, VOLCANO)
        result, seconds = self.search_until("volcano lava basalt", lambda r: r and r[0]["doc"] == "zz-test-volcano.md")
        self.assertEqual("zz-test-volcano.md", result[0]["doc"])
        self.assertLess(seconds, 10)
        self.assertMatchesBruteForce("volcano lava basalt")

    def test_editing_a_doc_moves_it_between_queries(self):
        helpers.write_atomic(TEST_DOC, VOLCANO)
        self.search_until("volcano lava basalt", lambda r: r and r[0]["doc"] == "zz-test-volcano.md")
        helpers.write_atomic(TEST_DOC, GLACIER)
        result, seconds = self.search_until("glacier ice valley", lambda r: r and r[0]["doc"] == "zz-test-volcano.md")
        self.assertEqual("zz-test-volcano.md", result[0]["doc"])
        self.assertLess(seconds, 10)
        volcano = self.assertMatchesBruteForce("volcano lava basalt")
        self.assertNotEqual("zz-test-volcano.md", volcano[0]["doc"])
        self.assertMatchesBruteForce("glacier ice valley")

    def test_deleting_a_doc_removes_it_from_results(self):
        helpers.write_atomic(TEST_DOC, VOLCANO)
        self.search_until("volcano lava basalt", lambda r: r and r[0]["doc"] == "zz-test-volcano.md")
        os.remove(TEST_DOC)
        result, seconds = self.search_until("volcano lava basalt", lambda r: "zz-test-volcano.md" not in names(r), k=10)
        self.assertNotIn("zz-test-volcano.md", names(result))
        self.assertLess(seconds, 10)
        self.assertMatchesBruteForce("volcano lava basalt", k=10)


if __name__ == "__main__":
    unittest.main()
