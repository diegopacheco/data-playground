import json
import os
import sys
import unittest
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))

import psycopg
from data import events

UI = os.environ.get("UI_URL", "http://localhost:8080")
MZ = os.environ.get("MZ_URL", "postgresql://materialize@localhost:31101/materialize")
NAMES = ["totals", "customer_totals", "region_revenue", "top_orders"]


def get(path):
    with urllib.request.urlopen(f"{UI}{path}", timeout=60) as r:
        return r.read().decode()


def tables(evs, keep_first_customer=False, ignore_deletes=False):
    orders, customers = {}, {}
    for e in evs:
        target = orders if e["topic"] == "orders" else customers
        if e["value"] is None:
            if not ignore_deletes:
                target.pop(e["key"], None)
        elif not (keep_first_customer and target is customers and e["key"] in customers):
            target[e["key"]] = e["value"]
    return orders, customers


def rows_sorted(rows):
    return sorted([list(r) for r in rows], key=lambda r: [str(v) for v in r])


def expected(evs, **kw):
    orders, customers = tables(evs, **kw)
    region_of = {c["customer_id"]: c["region"] for c in customers.values()}
    live = list(orders.values())
    by_customer, by_region = {}, {}
    for o in live:
        by_customer.setdefault(o["customer_id"], []).append(o["amount"])
        if o["customer_id"] in region_of:
            by_region.setdefault(region_of[o["customer_id"]], []).append(o)
    top = []
    for region, items in by_region.items():
        best = sorted(items, key=lambda o: (-o["amount"], o["order_id"]))[:3]
        top += [[region, o["order_id"], o["amount"], rank] for rank, o in enumerate(best, 1)]
    return {
        "totals": [[len(live), sum(o["amount"] for o in live) or None]],
        "customer_totals": rows_sorted([[c, len(a), sum(a)] for c, a in by_customer.items()]),
        "region_revenue": rows_sorted([[r, len(i), sum(o["amount"] for o in i)] for r, i in by_region.items()]),
        "top_orders": rows_sorted(top),
    }


def order_log_states(evs):
    live, states = {}, {(0, None)}
    for e in evs:
        if e["topic"] == "orders":
            if e["value"] is None:
                live.pop(e["key"], None)
            else:
                live[e["key"]] = e["value"]["amount"]
            states.add((len(live), sum(live.values()) or None))
    return states


def apply_mz(changelog):
    state = {}
    by_ts = {}
    for r in changelog:
        by_ts.setdefault(r[0], []).append(r)
    snapshots = []
    for ts in sorted(by_ts):
        for r in by_ts[ts]:
            key = tuple(r[2:])
            state[key] = state.get(key, 0) + r[1]
        snapshots.append((ts, rows_sorted([list(k) for k, d in state.items() for _ in range(max(d, 0))])))
    return snapshots


def apply_flink(changelog):
    state, after_each_add = [], []
    for r in changelog:
        if r[0] in ("INSERT", "UPDATE_AFTER"):
            state.append(list(r[1:]))
            after_each_add.append(rows_sorted(state))
        else:
            state.remove(list(r[1:]))
    return after_each_add


class MaterializeVsFlink(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = json.loads(get("/api/result"))
        assert cls.r, "no comparison result, run POST /api/run first"
        cls.evs = events()
        cls.want = expected(cls.evs)

    def test_input_has_updates_deletes_moves_and_a_tombstone_for_an_unknown_key(self):
        keys = [e["key"] for e in self.evs if e["topic"] == "orders" and e["value"] is not None]
        tombstones = [e["key"] for e in self.evs if e["topic"] == "orders" and e["value"] is None]
        self.assertGreater(len(keys), len(set(keys)), "without updates the upsert envelope is never exercised")
        self.assertGreaterEqual(len(tombstones), 10)
        self.assertIn("999", tombstones)
        self.assertNotIn("999", keys)
        self.assertNotEqual(self.want, expected(self.evs, ignore_deletes=True), "deletes must change the answer or the test could not catch a missed retraction")
        self.assertNotEqual(self.want["region_revenue"], expected(self.evs, keep_first_customer=True)["region_revenue"], "customer moves must change the join answer")

    def test_every_event_was_produced_and_ingested_by_materialize(self):
        produced = {t: sum(1 for e in self.evs if e["topic"] == t) for t in ["orders", "customers"]}
        offsets = self.r["materialize"]["offsets"]
        for logical, topic in self.r["topics"].items():
            self.assertEqual(offsets[topic]["produced"], produced[logical])
            self.assertEqual(offsets[topic]["ingested"], produced[logical])

    def test_materialize_real_time_recency_read_after_the_last_ack_is_complete(self):
        final = self.r["materialize"]["final"]["results"]
        for name in NAMES:
            self.assertEqual(final[name], self.want[name], f"materialize {name} differs from the independently computed answer")

    def test_flink_final_state_after_applying_its_changelog_is_correct(self):
        for name in NAMES:
            self.assertEqual(self.r["flink"]["results"][name], self.want[name], f"flink {name} differs from the independently computed answer")
            replayed = apply_flink(self.r["flink"]["changelog"][name])
            self.assertEqual(replayed[-1], self.want[name], f"flink {name} changelog does not replay to the answer")

    def test_materialize_views_still_answer_correctly_on_a_new_strict_serializable_read(self):
        with psycopg.connect(MZ, autocommit=True) as c:
            self.assertEqual(c.execute("SHOW transaction_isolation").fetchone()[0], "strict serializable")
            c.execute("BEGIN READ ONLY")
            got = {
                "totals": c.execute("SELECT order_count, total FROM totals").fetchall(),
                "customer_totals": c.execute("SELECT customer_id, order_count, total FROM customer_totals").fetchall(),
                "region_revenue": c.execute("SELECT region, order_count, revenue FROM region_revenue").fetchall(),
                "top_orders": c.execute("SELECT region, order_id, amount, rn FROM top_orders").fetchall(),
            }
            c.execute("COMMIT")
        for name in NAMES:
            self.assertEqual(rows_sorted([[v if v is None or isinstance(v, str) else int(v) for v in r] for r in got[name]]), self.want[name])

    def test_every_materialize_read_during_ingestion_was_a_consistent_snapshot(self):
        probes = self.r["materialize"]["probes"]
        states = order_log_states(self.evs)
        self.assertGreaterEqual(len(probes), 10, "too few reads during ingestion to say anything")
        self.assertEqual(self.r["materialize"]["probe_errors"], [])
        for ts, count, total, cust_count, cust_total, region_total, view_count, view_total in probes:
            self.assertEqual(count, cust_count, f"at {ts} customer_totals saw a different set of orders than orders")
            self.assertEqual(count, view_count, f"at {ts} totals saw a different set of orders than orders")
            self.assertEqual(total, cust_total, f"at {ts} customer_totals sum differs from the orders sum")
            self.assertEqual(total, region_total, f"at {ts} region_revenue (join) sum differs from the orders sum")
            self.assertEqual(total, view_total)
            self.assertIn((count, total or None), states, f"at {ts} materialize returned ({count}, {total}), a state that never existed in the orders log")
        self.assertGreater(len({(p[1], p[2]) for p in probes}), 3, "the probes must have seen ingestion in progress, not only the start and the end")

    def test_materialize_subscribe_changelog_replays_to_the_answer_with_only_real_states(self):
        states = order_log_states(self.evs)
        for name in NAMES:
            snaps = apply_mz(self.r["materialize"]["changelog"][name])
            self.assertEqual(snaps[-1][1], self.want[name], f"materialize {name} SUBSCRIBE does not replay to the answer")
        totals = apply_mz(self.r["materialize"]["changelog"]["totals"])
        self.assertGreater(len(totals), 3)
        for ts, rows in totals:
            self.assertEqual(len(rows), 1, f"at {ts} totals must hold exactly one row")
            self.assertIn(tuple(rows[0]), states, f"at {ts} materialize totals {rows[0]} never existed in the orders log")

    def test_flink_changelog_has_retractions_and_intermediate_totals_that_never_existed(self):
        kinds = self.r["flink"]["kinds"]
        for name in NAMES:
            self.assertGreater(kinds[name].get("UPDATE_BEFORE", 0), 0, f"flink {name} must retract old rows")
        states = order_log_states(self.evs)
        phantoms = [s for s in apply_flink(self.r["flink"]["changelog"]["totals"]) if tuple(s[0]) not in states]
        alive, updates = set(), 0
        for e in self.evs:
            if e["topic"] != "orders":
                continue
            if e["value"] is None:
                alive.discard(e["key"])
            else:
                updates += e["key"] in alive
                alive.add(e["key"])
        self.assertGreater(len(phantoms), 0, "flink emits -U then +U per input record, so an update is seen as a delete followed by an insert")
        self.assertLessEqual(len(phantoms), updates, "only an update of a live key can produce a state that never existed")

    def test_materialize_consolidates_its_changelog_and_flink_does_not(self):
        mz_rows = len(self.r["materialize"]["changelog"]["totals"])
        flink_rows = len(self.r["flink"]["changelog"]["totals"])
        order_events = sum(1 for e in self.evs if e["topic"] == "orders")
        self.assertGreater(flink_rows, order_events, "flink emits at least one changelog row per input record")
        self.assertLess(mz_rows, flink_rows, "materialize emits one consolidated diff per timestamp")

    def test_ui_page_has_every_tab(self):
        page = get("/")
        for tab in ["results", "changelog", "consistency", "events", "sql"]:
            self.assertIn(f'data-tab="{tab}"', page)


if __name__ == "__main__":
    unittest.main()
