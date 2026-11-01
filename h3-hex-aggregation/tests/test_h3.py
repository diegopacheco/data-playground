import json
import math
import os
import sys
import unittest
import urllib.error
import urllib.request
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))

import h3
from data import CITIES, GRID_STEP, POINTS, POINTS_PER_CITY, RESOLUTIONS

BASE = os.environ.get("APP_URL", "http://localhost:8080")


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=60) as r:
        return json.load(r)


def city_points(city):
    return [p for p in POINTS if p["city"] == city]


def recount(city, res):
    agg = defaultdict(lambda: [0, 0, 0])
    for p in city_points(city):
        a = agg[h3.latlng_to_cell(p["lat"], p["lng"], res)]
        a[0] += 1
        a[1] += p["fare_cents"]
        a[2] += p["wait_s"]
    return dict(agg)


def bit_parent(cell, res):
    value = int(cell, 16)
    child_res = (value >> 52) & 0xF
    value = (value & ~(0xF << 52)) | (res << 52)
    for r in range(res + 1, child_res + 1):
        value |= 0x7 << ((15 - r) * 3)
    return format(value, "x")


def inside(lat, lng, polygon):
    hit = False
    j = len(polygon) - 1
    for i in range(len(polygon)):
        yi, xi = polygon[i]
        yj, xj = polygon[j]
        if (yi > lat) != (yj > lat) and lng < (xj - xi) * (lat - yi) / (yj - yi) + xi:
            hit = not hit
        j = i
    return hit


def km(a, b):
    lat1, lng1, lat2, lng2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lng2 - lng1) / 2) ** 2
    return 2 * 6371.0088 * math.asin(math.sqrt(h))


def edge_neighbours(cell):
    ring = h3.cell_to_boundary(cell)
    clat, clng = h3.cell_to_latlng(cell)
    out = set()
    for i in range(len(ring)):
        a, b = ring[i], ring[(i + 1) % len(ring)]
        mlat, mlng = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
        out.add(h3.latlng_to_cell(clat + 1.5 * (mlat - clat), clng + 1.5 * (mlng - clng), h3.get_resolution(cell)))
    return out


def shared_vertices(a, b):
    vb = h3.cell_to_boundary(b)
    return sum(1 for p in h3.cell_to_boundary(a) if any(abs(p[0] - q[0]) < 1e-9 and abs(p[1] - q[1]) < 1e-9 for q in vb))


def km_to_polygon_edge(lat, lng, polygon):
    kx = 111.32 * math.cos(math.radians(lat))
    best = float("inf")
    for i in range(len(polygon)):
        (alat, alng), (blat, blng) = polygon[i], polygon[(i + 1) % len(polygon)]
        ax, ay, bx, by = (alng - lng) * kx, (alat - lat) * 110.57, (blng - lng) * kx, (blat - lat) * 110.57
        dx, dy = bx - ax, by - ay
        t = max(0.0, min(1.0, -(ax * dx + ay * dy) / (dx * dx + dy * dy)))
        best = min(best, math.hypot(ax + t * dx, ay + t * dy))
    return best


class H3AggregationTest(unittest.TestCase):
    def test_each_point_lies_inside_the_polygon_of_the_cell_it_was_indexed_to(self):
        for res in RESOLUTIONS:
            for p in POINTS:
                ring = list(h3.cell_to_boundary(h3.latlng_to_cell(p["lat"], p["lng"], res)))
                if not inside(p["lat"], p["lng"], ring):
                    self.assertLess(km_to_polygon_edge(p["lat"], p["lng"], ring), 0.001, (p["id"], res))

    def test_hexmap_counts_and_averages_equal_a_plain_recount_of_the_input(self):
        for city in CITIES:
            for res in RESOLUTIONS:
                expected = recount(city, res)
                got = {c["cell"]: c for c in get(f"/api/hexmap?city={city}&res={res}")["cells"] if c["n"] > 0}
                self.assertEqual(set(got), set(expected), (city, res))
                for cell, (n, fare, wait) in expected.items():
                    self.assertEqual(got[cell]["n"], n)
                    self.assertAlmostEqual(got[cell]["avg_fare"], fare / n, places=6)
                    self.assertAlmostEqual(got[cell]["avg_wait"], wait / n, places=6)
                self.assertEqual(sum(c["n"] for c in got.values()), POINTS_PER_CITY)

    def test_coarser_resolutions_have_fewer_and_fuller_cells(self):
        for city in CITIES:
            sizes = [len(recount(city, res)) for res in RESOLUTIONS]
            self.assertEqual(sizes, sorted(sizes), city)
            self.assertLess(sizes[0] * 7, sizes[-1])

    def test_k1_smoothing_is_the_mean_of_a_cell_and_its_six_edge_neighbours(self):
        for city in CITIES:
            counts = {c: v[0] for c, v in recount(city, 8).items()}
            got = {c["cell"]: c for c in get(f"/api/hexmap?city={city}&res=8")["cells"]}
            for cell in counts:
                nbs = edge_neighbours(cell)
                self.assertEqual(len(nbs), 6)
                for nb in nbs:
                    self.assertEqual(shared_vertices(cell, nb), 2)
                expected = (counts[cell] + sum(counts.get(nb, 0) for nb in nbs)) / 7
                self.assertAlmostEqual(got[cell]["smooth"], expected, places=9, msg=(city, cell))
            for cell, c in got.items():
                if c["n"] == 0:
                    self.assertTrue(any(nb in counts for nb in edge_neighbours(cell)), cell)
                    self.assertGreater(c["smooth"], 0)

    def test_rollup_parent_is_the_sum_of_its_children_by_index_bits(self):
        for city in CITIES:
            d = get(f"/api/rollup?city={city}")
            parents = defaultdict(lambda: [0, 0])
            for cell, (n, fare, _) in recount(city, 9).items():
                parents[bit_parent(cell, 7)][0] += n
                parents[bit_parent(cell, 7)][1] += fare
            top = max(parents, key=lambda c: (parents[c][0], c))
            self.assertEqual(d["parent"], top)
            self.assertEqual([d["rollup"]["n"], d["rollup"]["fare_sum"]], parents[top])
            self.assertAlmostEqual(d["rollup_avg_fare"], parents[top][1] / parents[top][0])
            self.assertEqual(len({c["cell"] for c in d["children"]}), 49)
            for child in d["children"]:
                self.assertEqual(bit_parent(child["cell"], 7), top)
                self.assertEqual(bit_parent(child["cell"], 8), child["mid"])
            self.assertEqual(sum(c["n"] for c in d["children"]), parents[top][0])
            self.assertEqual(len(d["mids"]), 7)
            self.assertEqual(sum(m["n"] for m in d["mids"]), parents[top][0])
            self.assertEqual(d["direct"]["n"], recount(city, 7)[top][0])

    def test_every_rollup_level_keeps_every_point_and_reports_the_fuzzy_containment(self):
        for city in CITIES:
            fine = {p["id"]: h3.latlng_to_cell(p["lat"], p["lng"], 9) for p in city_points(city)}
            for level in get(f"/api/rollup?city={city}")["levels"]:
                res = level["res"]
                self.assertEqual(level["rollup_total"], POINTS_PER_CITY)
                self.assertEqual(level["direct_total"], POINTS_PER_CITY)
                self.assertEqual(level["rollup_fare_sum"], sum(p["fare_cents"] for p in city_points(city)))
                moved = sum(1 for p in city_points(city) if bit_parent(fine[p["id"]], res) != h3.latlng_to_cell(p["lat"], p["lng"], res))
                self.assertEqual(level["mismatched_points"], moved, (city, res))
                if res < 9:
                    self.assertGreater(moved, 0)
                    self.assertLess(moved, POINTS_PER_CITY * 0.15)

    def test_k_ring_two_is_the_centre_six_edge_neighbours_and_twelve_beyond(self):
        for city in CITIES:
            d = get(f"/api/neighbours?city={city}")
            counts = {c: v[0] for c, v in recount(city, 8).items()}
            center = max(counts, key=lambda c: (counts[c], c))
            self.assertEqual(d["center"], center)
            rings = defaultdict(set)
            for c in d["cells"]:
                rings[c["ring"]].add(c["cell"])
                self.assertEqual(c["n"], counts.get(c["cell"], 0))
            ring1 = edge_neighbours(center)
            ring2 = set().union(*(edge_neighbours(c) for c in ring1)) - ring1 - {center}
            self.assertEqual(rings[0], {center})
            self.assertEqual(rings[1], ring1)
            self.assertEqual(rings[2], ring2)
            self.assertEqual(len(ring2), 12)
            self.assertAlmostEqual(d["smooth_k1"], (counts[center] + sum(counts.get(c, 0) for c in ring1)) / 7)
            self.assertAlmostEqual(d["smooth_k2"], sum(counts.get(c, 0) for c in ring1 | ring2 | {center}) / 19)
            spread = [km(h3.cell_to_latlng(center), h3.cell_to_latlng(c)) for c in ring1]
            self.assertAlmostEqual(d["hex_neighbour_km"]["min"], min(spread), places=9)
            self.assertLess(max(spread) / min(spread), 1.1)

    def test_polyfill_is_every_cell_whose_centre_is_inside_the_region(self):
        for city, c in CITIES.items():
            polygon = c["region"]
            lats, lngs = [v[0] for v in polygon], [v[1] for v in polygon]
            for res in (8, 9):
                step = 0.0004
                candidates = {
                    h3.latlng_to_cell(min(lats) - 0.01 + i * step, min(lngs) - 0.01 + j * step, res)
                    for i in range(int((max(lats) - min(lats) + 0.02) / step) + 1)
                    for j in range(int((max(lngs) - min(lngs) + 0.02) / step) + 1)
                }
                expected = {cell for cell in candidates if inside(*h3.cell_to_latlng(cell), polygon)}
                got = {x["cell"] for x in get(f"/api/region?city={city}&res={res}")["cells"]}
                self.assertEqual(got, expected, (city, res))

    def test_point_in_region_by_cell_only_disagrees_with_the_exact_test_near_the_edge(self):
        for city, c in CITIES.items():
            polygon = c["region"]
            agreement = {}
            for res in (8, 9):
                d = get(f"/api/region?city={city}&res={res}")
                exact = {p["id"] for p in city_points(city) if inside(p["lat"], p["lng"], polygon)}
                by_cell = {p["id"] for p in city_points(city) if inside(*h3.cell_to_latlng(h3.latlng_to_cell(p["lat"], p["lng"], res)), polygon)}
                self.assertEqual(d["exact"], len(exact))
                self.assertEqual(d["hex"], len(by_cell))
                self.assertEqual(d["only_exact"], len(exact - by_cell))
                self.assertEqual(d["only_hex"], len(by_cell - exact))
                edge_km = h3.average_hexagon_edge_length(res, "km")
                for p in city_points(city):
                    if (p["id"] in exact) != (p["id"] in by_cell):
                        self.assertLess(km_to_polygon_edge(p["lat"], p["lng"], polygon), 1.2 * edge_km, p["id"])
                agreement[res] = len(exact & by_cell) / len(exact | by_cell)
            self.assertGreater(agreement[8], 0.75, city)
            self.assertGreater(agreement[9], agreement[8], city)

    def test_naive_grid_counts_and_its_latitude_distortion(self):
        all_cities = get("/api/compare-all")
        for city in CITIES:
            d = get(f"/api/compare?city={city}")
            expected = defaultdict(int)
            for p in city_points(city):
                expected[(math.floor(p["lat"] / GRID_STEP), math.floor(p["lng"] / GRID_STEP))] += 1
            self.assertEqual({(g["row"], g["col"]): g["n"] for g in d["grid"]}, dict(expected))
            self.assertEqual(sum(h["n"] for h in d["hex"]), POINTS_PER_CITY)
            self.assertGreater(d["grid_neighbour_km"]["max"] / d["grid_neighbour_km"]["min"], 1.4)
            self.assertLess(d["hex_neighbour_km"]["max"] / d["hex_neighbour_km"]["min"], 1.1)
        mid = lambda k: (CITIES[k]["box"][0] + CITIES[k]["box"][2]) / 2
        expected_ratio = math.cos(math.radians(mid("london"))) / math.cos(math.radians(mid("sf")))
        got_ratio = all_cities["london"]["grid_km2"]["mean"] / all_cities["sf"]["grid_km2"]["mean"]
        self.assertAlmostEqual(got_ratio, expected_ratio, delta=0.02)

    def test_h3_py_and_duckdb_agree_on_every_check(self):
        d = get("/api/crosscheck")
        self.assertTrue(d["all_equal"], [c for c in d["checks"] if not c["equal"]])
        self.assertEqual(len(d["checks"]), len(CITIES) * (len(RESOLUTIONS) + 2 * (len(RESOLUTIONS) - 1) + 2 + 4))

    def test_bad_input_is_rejected(self):
        for path in ("/api/hexmap?city=paris", "/api/hexmap?res=3", "/api/region?res=7"):
            with self.assertRaises(urllib.error.HTTPError) as e:
                get(path)
            self.assertEqual(e.exception.code, 400)

    def test_ui_page_has_every_tab(self):
        with urllib.request.urlopen(BASE + "/", timeout=10) as r:
            page = r.read().decode()
        for tab in ("map", "rollup", "neighbours", "region", "grid", "check"):
            self.assertIn(f'data-tab="{tab}"', page)


if __name__ == "__main__":
    unittest.main()
