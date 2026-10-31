import itertools
import json
import os
import sys
import unittest
import urllib.request
from collections import Counter, defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
import data
import feldera

UI = os.environ.get("UI_URL", "http://localhost:8080")


def get(path):
    with urllib.request.urlopen(UI + path, timeout=60) as resp:
        return resp.read()


def hour(ts):
    return ts[:13].replace(" ", "T") + ":00:00"


def totals(orders):
    out = defaultdict(lambda: [0, 0])
    for o in orders:
        out[o["region"]][0] += 1
        out[o["region"]][1] += o["amount"]
    return Counter({(r, c, s) for r, (c, s) in out.items()})


def windows(orders):
    out = defaultdict(lambda: [0, 0])
    for o in orders:
        out[(hour(o["ts"]), o["region"])][0] += 1
        out[(hour(o["ts"]), o["region"])][1] += o["amount"]
    return Counter({(w, r, c, s) for (w, r), (c, s) in out.items()})


def closure(edges):
    reach = set()
    for start in {s for s, _ in edges}:
        frontier = [start]
        seen = set()
        while frontier:
            node = frontier.pop()
            for s, d in edges:
                if s == node and d not in seen:
                    seen.add(d)
                    frontier.append(d)
        reach.update((start, d) for d in seen)
    return Counter(reach)


def total_rows(rows):
    return Counter((r["region"], int(r["orders"]), int(r["revenue"])) for r in rows)


def iso(ts):
    return ts.replace(" ", "T")


def window_rows(rows):
    return Counter((iso(r["window_start"]), r["region"], int(r["orders"]), int(r["revenue"])) for r in rows)


def edge_rows(rows):
    return Counter((r["src"], r["dst"]) for r in rows)


def as_delta(changes, shape):
    out = Counter()
    for c in changes:
        out[next(iter(shape([c["row"]])))] += c["weight"]
    return Counter({k: v for k, v in out.items() if v})


def diff(before, after):
    out = Counter(after)
    out.subtract(before)
    return Counter({k: v for k, v in out.items() if v})


def expected_states():
    orders, edges = {}, set()
    states = []

    def snap():
        states.append((totals(orders.values()), windows(orders.values()), closure(edges)))

    for i in range(1, 61):
        orders[i] = data.order(i)
        if i in (40, 60):
            snap()
    for i in range(5, 51, 5):
        del orders[i]
    snap()
    for i in (1, 2, 3):
        orders[i] = {**data.order(i), "amount": 9_000 + i}
    snap()
    edges.update(data.GRAPH)
    snap()
    edges.discard((3, 4))
    snap()
    edges.add((9, 10))
    snap()
    edges.discard((6, 3))
    edges.add((6, 1))
    snap()
    return orders, edges, states


class ChangesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = json.loads(get("/api/results"))["changes"]
        cls.orders, cls.edges, cls.states = expected_states()

    def test_views_equal_an_independent_answer_after_inserts_deletes_and_updates(self):
        self.assertEqual(total_rows(feldera.query("SELECT * FROM region_totals")), totals(self.orders.values()))
        self.assertEqual(window_rows(feldera.query("SELECT * FROM hourly_revenue")), windows(self.orders.values()))

    def test_recursive_view_equals_a_bfs_transitive_closure_after_edge_deletes(self):
        live = edge_rows(feldera.query("SELECT * FROM reachable"))
        self.assertEqual(live, closure(self.edges))
        self.assertIn((6, 1), live)
        self.assertNotIn((1, 4), live)

    def test_every_step_streams_exactly_the_difference_between_two_states(self):
        steps = self.result["steps"]
        self.assertEqual(len(steps), len(self.states))
        empty = (Counter(), Counter(), Counter())
        for before, after, step in zip([empty] + self.states[:-1], self.states, steps):
            with self.subTest(step=step["label"]):
                self.assertEqual(as_delta(step["deltas"]["region_totals"], total_rows), diff(before[0], after[0]))
                self.assertEqual(as_delta(step["deltas"]["hourly_revenue"], window_rows), diff(before[1], after[1]))
                self.assertEqual(as_delta(step["deltas"]["reachable"], edge_rows), diff(before[2], after[2]))

    def test_streamed_weights_integrate_to_the_view_snapshot(self):
        for view, shape in (("region_totals", total_rows), ("hourly_revenue", window_rows), ("reachable", edge_rows)):
            integrated = as_delta(self.result["streamed"][view], shape)
            self.assertTrue(all(w == 1 for w in integrated.values()), view)
            self.assertEqual(integrated, shape(self.result["snapshot"][view]), view)

    def test_breaking_the_cycle_retracts_every_path_that_used_the_deleted_edge(self):
        step = next(s for s in self.result["steps"] if s["label"] == "delete edge 3 -> 4")
        delta = as_delta(step["deltas"]["reachable"], edge_rows)
        self.assertTrue(all(w == -1 for w in delta.values()))
        self.assertIn((3, 3), delta)
        self.assertIn((1, 4), delta)
        self.assertEqual(delta, diff(self.states[4][2], self.states[5][2]))

    def test_an_update_only_touches_the_windows_of_the_updated_orders(self):
        step = next(s for s in self.result["steps"] if s["label"].startswith("update"))
        touched = {iso(c["row"]["window_start"]) for c in step["deltas"]["hourly_revenue"]}
        self.assertEqual(touched, {hour(data.order(i)["ts"]) for i in (1, 2, 3)})
        self.assertEqual(sorted(c["weight"] for c in step["deltas"]["region_totals"]).count(-1), len({data.order(i)["region"] for i in (1, 2, 3)}))


class ScalingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = json.loads(get("/api/results"))["scaling"]

    def test_final_views_equal_an_independent_recompute_of_a_million_rows(self):
        final = self.result["final"]
        deleted = set(final["deleted_ids"])
        ids = [i for i in itertools.chain(range(*final["loaded_ids"]), range(*final["inserted_ids"])) if i not in deleted]
        self.assertEqual(len(ids), final["rows"])
        self.assertEqual(total_rows(final["region_totals"]), totals(map(data.order, ids)))
        self.assertEqual(window_rows(final["hourly_revenue"]), windows(map(data.order, ids)))

    def test_a_fixed_change_produces_the_same_output_work_at_every_table_size(self):
        sizes = self.result["by_size"]
        self.assertEqual(sizes[-1]["rows"] // sizes[0]["rows"], 16)
        self.assertEqual(len({s["output_changes"] for s in sizes}), 1)
        self.assertLessEqual(sizes[0]["output_changes"], 2 * 20 + 2 * len(data.REGIONS))

    def test_full_recompute_grows_with_the_table_while_the_delta_stays_small(self):
        small, large = self.result["by_size"][0], self.result["by_size"][-1]
        self.assertGreater(large["python_full_ms"], 5 * small["python_full_ms"])
        self.assertGreater(large["duckdb_full_ms"], 2 * small["duckdb_full_ms"])
        self.assertLess(large["feldera_delta_ms"], large["python_full_ms"] / 5)
        self.assertLess(large["feldera_delta_ms"], large["duckdb_full_ms"])

    def test_delta_cost_grows_with_the_size_of_the_change(self):
        deltas = self.result["by_delta"]
        self.assertEqual([d["changed_rows"] for d in deltas], [10, 100, 1_000, 10_000, 100_000])
        self.assertGreater(deltas[-1]["feldera_delta_ms"], 10 * deltas[0]["feldera_delta_ms"])


class UiTest(unittest.TestCase):
    def test_ui_page_has_every_tab(self):
        page = get("/").decode()
        for tab in ("pipeline", "deltas", "recursive", "windows", "scaling"):
            self.assertIn(f'data-tab="{tab}"', page)


if __name__ == "__main__":
    unittest.main()
