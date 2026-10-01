import csv
import json
import sys
import tempfile
import unittest
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "dataflow"))

from bytewax import operators as op
from bytewax.dataflow import Dataflow
from bytewax.recovery import RecoveryConfig, init_db_dir
from bytewax.testing import TestingSink, TestingSource, run_main

from core import aggregate

with open(ROOT / "data" / "orders.csv", newline="") as f:
    ROWS = list(csv.DictReader(f))
RAW = [json.dumps(r) for r in ROWS]


def expected_totals():
    out = {}
    for r in ROWS:
        o, q, c = out.get(r["category"], (0, 0, Decimal(0)))
        out[r["category"]] = (o + 1, q + int(r["quantity"]), c + int(r["quantity"]) * Decimal(r["price"]) * 100)
    return {k: (o, q, int(c)) for k, (o, q, c) in out.items()}


def expected_windows():
    out = {}
    for r in ROWS:
        key = (r["category"], r["ts"][:10] + "T00:00:00Z")
        o, q, c = out.get(key, (0, 0, Decimal(0)))
        out[key] = (o + 1, q + int(r["quantity"]), c + int(r["quantity"]) * Decimal(r["price"]) * 100)
    return {k: (o, q, int(c)) for k, (o, q, c) in out.items()}


def last_day_per_category():
    last = {}
    for r in ROWS:
        last[r["category"]] = max(last.get(r["category"], ""), r["ts"][:10] + "T00:00:00Z")
    return last


def build(items):
    got = []
    flow = Dataflow("test")
    op.output("out", aggregate(op.input("in", flow, TestingSource(items))), TestingSink(got))
    return flow, got


def final_totals(records):
    out = {}
    for r in records:
        if r["kind"] == "total":
            out[r["category"]] = (r["orders"], r["quantity"], r["revenue_cents"])
    return out


def windows(records):
    return {(r["category"], r["window_start"]): (r["orders"], r["quantity"], r["revenue_cents"]) for r in records if r["kind"] == "window"}


class RunningTotalsTest(unittest.TestCase):
    def test_final_running_total_per_category_equals_whole_csv(self):
        flow, got = build(RAW)
        run_main(flow)
        self.assertEqual(final_totals(got), expected_totals())

    def test_running_total_grows_one_order_at_a_time(self):
        flow, got = build(RAW)
        run_main(flow)
        seen = {}
        for r in got:
            if r["kind"] == "total":
                self.assertEqual(r["orders"], seen.get(r["category"], 0) + 1)
                seen[r["category"]] = r["orders"]


class DailyWindowTest(unittest.TestCase):
    def test_bounded_input_flushes_every_daily_window_with_exact_sums(self):
        flow, got = build(RAW)
        run_main(flow)
        self.assertEqual(windows(got), expected_windows())

    def test_open_stream_keeps_only_latest_day_per_category_open(self):
        flow, got = build(RAW + [TestingSource.ABORT()])
        run_main(flow)
        last = last_day_per_category()
        closed = {k: v for k, v in expected_windows().items() if last[k[0]] != k[1]}
        self.assertEqual(windows(got), closed)


class RecoveryTest(unittest.TestCase):
    def test_crash_and_resume_does_not_double_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            init_db_dir(tmp, 1)
            flow, got = build(RAW[:120] + [TestingSource.ABORT()] + RAW[120:])
            config = RecoveryConfig(tmp)
            run_main(flow, epoch_interval=timedelta(0), recovery_config=config)
            self.assertEqual(sum(v[0] for v in final_totals(got).values()), 120)
            before = len(got)
            run_main(flow, epoch_interval=timedelta(0), recovery_config=config)
            replayed = sum(1 for r in got[before:] if r["kind"] == "total")
            self.assertLess(replayed, len(RAW))
            self.assertGreaterEqual(replayed, len(RAW) - 120)
            self.assertEqual(final_totals(got), expected_totals())
            self.assertEqual(windows(got), expected_windows())


if __name__ == "__main__":
    unittest.main()
