import base64
import csv
import io
import json
import os
import unittest
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

import pyarrow.parquet as pq
from PIL import Image

DATA = Path(os.environ.get("DATA_DIR", "/app/data"))
OUTPUT = Path(os.environ.get("OUTPUT_DIR", "/app/output"))
UI_URL = os.environ.get("UI_URL", "http://localhost:27000")
THUMBNAIL = 128
BRIGHT = 70

ROWS = list(csv.DictReader((DATA / "products.csv").open(newline="")))
BY_ID = {int(r["id"]): r for r in ROWS}
PROMOTIONS = {r["color"]: int(r["discount_pct"]) for r in csv.DictReader((DATA / "promotions.csv").open(newline=""))}
TABLE = pq.read_table(OUTPUT / "products").to_pylist()
OUT = {r["id"]: r for r in TABLE}


def get(path, **params):
    with urllib.request.urlopen(f"{UI_URL}{path}?{urllib.parse.urlencode(params)}", timeout=120) as r:
        return json.load(r)


def png(data):
    return Image.open(io.BytesIO(data))


def pixel_mode(image):
    return Counter(image.convert("RGB").get_flattened_data()).most_common(1)[0][0]


def hue_family(rgb):
    r, g, b = rgb
    if max(rgb) - min(rgb) < 40:
        return "neutral"
    if r >= g and r >= b:
        return "red" if g < r * 0.4 and b < r * 0.4 else "warm"
    return "other"


class ParquetOutputTest(unittest.TestCase):
    def test_every_csv_row_is_exactly_one_parquet_row(self):
        self.assertEqual(sorted(r["id"] for r in TABLE), sorted(BY_ID), "a rerun must overwrite, never append or drop products")

    def test_every_product_has_one_thumbnail_of_the_target_size(self):
        for pid, row in OUT.items():
            image = png(row["thumbnail_png"])
            self.assertEqual(image.size, (THUMBNAIL, THUMBNAIL), f"product {pid} thumbnail must be normalized for the grid")
            self.assertEqual(len(row["thumbnail"]), THUMBNAIL * THUMBNAIL * 3, "the daft image column holds 128x128 RGB pixels")

    def test_thumbnail_is_the_resized_source_image_of_that_product(self):
        for pid, row in OUT.items():
            source = Image.open(DATA / BY_ID[pid]["image_path"])
            self.assertEqual((row["width"], row["height"]), source.size, "width and height come from the decoded source image")
            self.assertEqual(pixel_mode(png(row["thumbnail_png"])), pixel_mode(source), f"product {pid} thumbnail belongs to another image")

    def test_source_images_have_different_sizes_so_resize_matters(self):
        self.assertGreater(len({(r["width"], r["height"]) for r in TABLE}), 10)

    def test_detected_color_matches_the_color_the_image_was_drawn_with(self):
        for pid, row in OUT.items():
            self.assertEqual(row["dominant_color"], BY_ID[pid]["color"], f"product {pid} color must come from its pixels")

    def test_brightness_separates_light_and_dark_images(self):
        for pid, row in OUT.items():
            self.assertEqual(row["brightness"] >= BRIGHT, BY_ID[pid]["tone"] == "light", f"product {pid} brightness {row['brightness']}")

    def test_ground_truth_color_columns_are_not_copied_into_the_output(self):
        self.assertNotIn("color", TABLE[0], "the pipeline must derive color from pixels, not from the csv")
        self.assertNotIn("tone", TABLE[0])

    def test_promotion_join_prices_follow_the_detected_color(self):
        for pid, row in OUT.items():
            discount = PROMOTIONS.get(BY_ID[pid]["color"], 0)
            self.assertEqual(row["discount_pct"], discount, f"product {pid}")
            self.assertAlmostEqual(row["sale_price"], round(float(BY_ID[pid]["price"]) * (100 - discount) / 100, 2))

    def test_embeddings_are_unit_vectors_of_the_model_size(self):
        for row in TABLE:
            self.assertEqual(len(row["embedding"]), 384)
            self.assertAlmostEqual(sum(v * v for v in row["embedding"]), 1.0, places=3)


class QueryTest(unittest.TestCase):
    def test_bright_red_under_50_returns_exactly_the_matching_products(self):
        r = get("/api/products", color="red", min_brightness=BRIGHT, max_price=50)
        expected = {pid for pid, row in BY_ID.items() if row["color"] == "red" and row["tone"] == "light" and float(row["price"]) <= 50}
        self.assertEqual({p["id"] for p in r["rows"]}, expected)
        self.assertEqual(len(expected), 4)

    def test_red_filter_thumbnails_are_really_red(self):
        rows = get("/api/products", color="red")["rows"]
        self.assertEqual(len(rows), sum(1 for row in ROWS if row["color"] == "red"))
        for p in rows:
            image = png(base64.b64decode(p["thumbnail"].split(",", 1)[1]))
            self.assertEqual(hue_family(pixel_mode(image)), "red", f"{p['name']} thumbnail is not red")

    def test_dark_filter_excludes_every_light_image(self):
        rows = get("/api/products", max_brightness=65)["rows"]
        self.assertEqual({p["id"] for p in rows}, {pid for pid, row in BY_ID.items() if row["tone"] == "dark"})

    def test_filters_are_pushed_down_into_the_parquet_scan(self):
        plan = get("/api/products", color="red", max_price=50)["plan"]
        optimized = plan.split("== Optimized Logical Plan ==")[1]
        self.assertIn("Filter pushdown", optimized, "daft should filter inside the scan, not after reading every row")
        self.assertIn("dominant_color", optimized.split("Filter pushdown")[1].splitlines()[0])
        self.assertIn("Projection pushdown", optimized, "the embedding column must not be read when it is not needed")
        self.assertNotIn("embedding", optimized.split("Projection pushdown")[1].splitlines()[0])

    def test_semantic_query_with_color_filter_ranks_the_sleeping_bag_first(self):
        rows = get("/api/products", q="stay warm in freezing winter", color="blue")["rows"]
        self.assertEqual(rows[0]["name"], "Down Sleeping Bag")
        self.assertTrue(all(p["dominant_color"] == "blue" for p in rows))
        scores = [p["similarity"] for p in rows]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_color_filter_changes_the_semantic_winner(self):
        unfiltered = get("/api/products", q="keep my head warm in snowy weather")["rows"]
        blue = get("/api/products", q="keep my head warm in snowy weather", color="blue")["rows"]
        self.assertEqual(unfiltered[0]["name"], "Wool Beanie")
        self.assertNotIn("Wool Beanie", [p["name"] for p in blue], "the beanie image is red, a blue filter must drop it")

    def test_every_preset_runs_and_returns_rows(self):
        for preset in get("/api/info")["presets"]:
            self.assertGreater(get("/api/products", **preset["params"])["count"], 0, preset["id"])


class GroupbyAndPipelineTest(unittest.TestCase):
    def test_groupby_totals_per_category_match_the_csv(self):
        groups = get("/api/groupby")["rows"]
        counts, totals = defaultdict(int), defaultdict(float)
        for g in groups:
            counts[g["category"]] += g["products"]
            totals[g["category"]] += g["total_price"]
        expected_counts, expected_totals = Counter(r["category"] for r in ROWS), defaultdict(float)
        for r in ROWS:
            expected_totals[r["category"]] += float(r["price"])
        self.assertEqual(dict(counts), dict(expected_counts))
        for category, total in expected_totals.items():
            self.assertAlmostEqual(totals[category], total, places=2)

    def test_groupby_color_counts_match_the_drawn_colors(self):
        groups = get("/api/groupby")["rows"]
        self.assertEqual(Counter({(g["category"], g["dominant_color"]): g["products"] for g in groups}),
                         Counter((r["category"], r["color"]) for r in ROWS))

    def test_pipeline_recorded_every_stage_and_a_lazy_plan(self):
        run = json.loads((OUTPUT / "run.json").read_text())
        stages = [s["stage"] for s in run["stages"]]
        self.assertEqual(stages[0], "read csv")
        self.assertEqual(stages[-1], "write parquet")
        self.assertEqual(len(stages), 7)
        self.assertTrue(all(s["ms"] > 0 and s["rows"] == len(ROWS) for s in run["stages"]))
        self.assertEqual(run["runner"], "native")
        self.assertIn("url_download", run["plan"])
        self.assertIn("image_resize", run["plan"])
        self.assertIn("== Physical Plan ==", run["plan"])


if __name__ == "__main__":
    unittest.main()
