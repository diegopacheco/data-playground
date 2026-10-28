import json
import os
import unittest
import urllib.error
import urllib.request

from confluent_kafka import Consumer, TopicPartition

API = os.environ.get("API_URL", "http://localhost:8080")
BROKERS = os.environ.get("BROKERS", "r13-redpanda:9092")
TOPIC = os.environ.get("TOPIC", "orders")


def call(path, method="GET"):
    req = urllib.request.Request(API + path, method=method)
    with urllib.request.urlopen(req, timeout=300) as resp:
        return json.loads(resp.read())


def status_of(path, method="POST"):
    try:
        call(path, method)
        return 200
    except urllib.error.HTTPError as e:
        e.close()
        return e.code


def read_log():
    c = Consumer({"bootstrap.servers": BROKERS, "group.id": "r13-test-oracle", "enable.auto.commit": False})
    try:
        end = c.get_watermark_offsets(TopicPartition(TOPIC, 0), timeout=10)[1]
        c.assign([TopicPartition(TOPIC, 0, 0)])
        out = []
        while len(out) < end:
            msgs = c.consume(end - len(out), timeout=10)
            if not msgs:
                raise AssertionError("could not read the whole topic")
            out += [(m.offset(), json.loads(m.value())) for m in msgs if not m.error()]
        return out[:end]
    finally:
        c.close()


def expected(log, logic, start=0, end=None, day=None, exclude=frozenset()):
    end = len(log) if end is None else end
    firsts = {}
    for offset, e in log[start:end]:
        if e["event_id"] not in exclude and e["event_id"] not in firsts:
            firsts[e["event_id"]] = e
    table = {}
    for e in firsts.values():
        if day and e["ts"][:10] != day:
            continue
        key = (e["ts"][:10], e["store"])
        sales, refunds, revenue = table.get(key, (0, 0, 0))
        if e["kind"] == "sale":
            table[key] = (sales + 1, refunds, revenue + e["amount_cents"])
        else:
            signed = -e["amount_cents"] if logic == "v2" else e["amount_cents"]
            table[key] = (sales, refunds + 1, revenue + signed)
    return [[d, s, *v] for (d, s), v in sorted(table.items())]


def ids_before(log, offset):
    return frozenset(e["event_id"] for _, e in log[:offset])


class ScenarioTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = call("/api/scenario")
        cls.steps = {s["id"]: s for s in cls.report["steps"]}
        cls.log = read_log()
        cls.day = cls.report["days"][0]
        cls.watermark1 = cls.steps["lambda-nightly-1"]["extra"]["batch"]["watermark"]
        cls.watermark2 = cls.steps["lambda-nightly-2"]["extra"]["batch"]["watermark"]

    def snap(self, step):
        return self.steps[step]["snapshot"]

    def test_log_really_contains_resends_and_late_events(self):
        ids = [e["event_id"] for _, e in self.log]
        self.assertGreater(len(ids) - len(set(ids)), 0)
        latest_day = ""
        late = 0
        for _, e in self.log:
            if e["ts"][:10] < latest_day:
                late += 1
            latest_day = max(latest_day, e["ts"][:10])
        self.assertGreaterEqual(late, 100)

    def test_app_truth_in_every_step_matches_an_independent_recompute_of_the_log(self):
        for step in self.report["steps"]:
            end = step["snapshot"]["log_end_offset"]
            self.assertEqual(step["snapshot"]["truth_v1"], expected(self.log, "v1", end=end), step["id"])
            self.assertEqual(step["snapshot"]["truth_v2"], expected(self.log, "v2", end=end), step["id"])

    def test_resends_are_counted_once(self):
        s = self.snap("after-fix")
        distinct = len({e["event_id"] for _, e in self.log[: s["log_end_offset"]]})
        self.assertEqual(sum(r[2] + r[3] for r in s["lambda_serving"]), distinct)
        self.assertEqual(sum(r[2] + r[3] for r in s["kappa_serving"]), distinct)

    def test_late_data_is_served_by_lambda_speed_layer_until_the_next_batch(self):
        s = self.snap("late-data")
        end = s["log_end_offset"]
        self.assertEqual(s["lambda_batch"], expected(self.log, "v1", end=self.watermark1))
        self.assertEqual(s["lambda_speed"], expected(self.log, "v1", start=self.watermark1, end=end, exclude=ids_before(self.log, self.watermark1)))
        self.assertEqual(s["lambda_serving"], expected(self.log, "v1", end=end))
        self.assertNotEqual([r for r in s["lambda_batch"] if r[0] == self.day], expected(self.log, "v1", end=end, day=self.day))
        after = self.snap("lambda-nightly-2")
        self.assertEqual(after["lambda_batch"], expected(self.log, "v1", end=self.watermark2))
        self.assertEqual(after["lambda_speed"], [])

    def test_late_data_updates_the_old_day_in_place_in_kappa(self):
        s = self.snap("late-data")
        self.assertEqual(s["kappa_serving"], expected(self.log, "v1", end=s["log_end_offset"]))

    def test_lambda_day_backfill_twice_is_identical_and_equals_the_master_up_to_the_watermark(self):
        extra = self.steps["lambda-backfill-day"]["extra"]
        self.assertEqual(extra["run1"]["checksum"], extra["run2"]["checksum"])
        self.assertEqual(extra["run1"]["rows"], extra["run2"]["rows"])
        self.assertEqual(extra["run1"]["rows"], expected(self.log, "v1", end=self.watermark1, day=self.day))

    def test_kappa_day_backfill_twice_is_identical_and_equals_the_log(self):
        extra = self.steps["kappa-backfill-day"]["extra"]
        end = self.snap("kappa-backfill-day")["log_end_offset"]
        self.assertEqual(extra["run1"]["checksum"], extra["run2"]["checksum"])
        self.assertEqual(extra["run2"]["rows"], expected(self.log, "v1", end=end, day=self.day))

    def test_redelivering_the_whole_log_changes_nothing(self):
        s = self.snap("redelivery")
        before = self.snap("kappa-backfill-day")
        self.assertEqual(s["lambda_serving"], before["lambda_serving"])
        self.assertEqual(s["kappa_serving"], before["kappa_serving"])
        self.assertEqual(self.steps["redelivery"]["extra"]["master_rows"], len({e["event_id"] for _, e in self.log[: s["log_end_offset"]]}))

    def test_lambda_batch_only_fix_is_wrong_exactly_where_the_speed_layer_saw_refunds(self):
        s = self.snap("lambda-fix-batch")
        end = s["log_end_offset"]
        seen = ids_before(self.log, self.watermark2)
        refund_keys = set()
        for _, e in self.log[self.watermark2:end]:
            if e["kind"] == "refund" and e["event_id"] not in seen:
                refund_keys.add((e["ts"][:10], e["store"]))
        truth = {(r[0], r[1]): r for r in expected(self.log, "v2", end=end)}
        wrong = {(r[0], r[1]) for r in s["lambda_serving"] if truth[(r[0], r[1])] != r}
        self.assertTrue(refund_keys)
        self.assertEqual(wrong, refund_keys)
        self.assertEqual(s["lambda_batch"], expected(self.log, "v2", end=self.watermark2))

    def test_lambda_is_right_only_after_the_second_fix(self):
        s = self.snap("lambda-fix-speed")
        self.assertEqual(s["lambda_serving"], expected(self.log, "v2", end=s["log_end_offset"]))

    def test_kappa_replay_twice_is_identical_and_v1_serves_until_the_swap(self):
        extra = self.steps["kappa-replay"]["extra"]
        s = self.snap("kappa-replay")
        end = s["log_end_offset"]
        self.assertEqual(extra["run1"]["checksum"], extra["run2"]["checksum"])
        self.assertEqual(extra["run1"]["rows"], expected(self.log, "v2", end=end))
        self.assertEqual(extra["run1"]["events_replayed"], end)
        self.assertEqual(s["kappa_serving"], expected(self.log, "v1", end=end))
        self.assertEqual(self.snap("kappa-swap")["kappa_serving"], expected(self.log, "v2", end=end))

    def test_both_architectures_end_with_the_fixed_numbers(self):
        s = self.snap("after-fix")
        truth = expected(self.log, "v2", end=s["log_end_offset"])
        self.assertEqual(s["lambda_serving"], truth)
        self.assertEqual(s["kappa_serving"], truth)
        self.assertTrue(self.report["ok"])

    def test_compare_counts_one_logic_for_kappa_and_two_for_lambda(self):
        c = self.report["compare"]
        self.assertEqual(c["lambda"]["logic_implementations"], len(c["lambda"]["logic_code"]))
        self.assertEqual(c["kappa"]["logic_implementations"], len(c["kappa"]["logic_code"]))
        self.assertGreater(c["lambda"]["wrong_rows_during_fix"], 0)
        s = self.snap("bug-found")
        refunds = sum(e["amount_cents"] for e in {e["event_id"]: e for _, e in reversed(self.log[: s["log_end_offset"]])}.values() if e["kind"] == "refund")
        self.assertEqual(c["bug_overstatement_cents"], 2 * refunds)


class LiveApiTest(unittest.TestCase):
    def test_live_late_events_reach_both_serving_tables(self):
        sent = call("/api/produce?kind=late&count=30", "POST")
        self.assertGreaterEqual(sent["sent"], 30)
        log = read_log()
        truth = expected(log, "v2")
        self.assertEqual(call("/api/lambda/serving"), truth)
        self.assertEqual(call("/api/kappa/serving"), truth)

    def test_rest_backfills_twice_are_identical(self):
        day = call("/api/scenario")["days"][1]
        a = call(f"/api/lambda/backfill?day={day}", "POST")
        b = call(f"/api/lambda/backfill?day={day}", "POST")
        self.assertEqual(a["checksum"], b["checksum"])
        log = read_log()
        self.assertEqual(b["rows"], expected(log, "v2", end=b["watermark"], day=day))
        k1 = call(f"/api/kappa/backfill?day={day}", "POST")
        k2 = call(f"/api/kappa/backfill?day={day}", "POST")
        self.assertEqual(k1["checksum"], k2["checksum"])
        self.assertEqual(k2["rows"], expected(log, "v2", end=k2["events_replayed"], day=day))

    def test_serving_version_cannot_be_rebuilt_in_place(self):
        active = call("/api/state")["kappa"]["active"]
        self.assertEqual(status_of(f"/api/kappa/replay?version={active}&logic=v2"), 400)

    def test_ui_has_every_tab(self):
        with urllib.request.urlopen(API + "/", timeout=10) as resp:
            page = resp.read().decode()
        for tab in ["timeline", "idempotency", "late", "bugfix", "compare", "live"]:
            self.assertIn(f'data-tab="{tab}"', page)


if __name__ == "__main__":
    unittest.main()
