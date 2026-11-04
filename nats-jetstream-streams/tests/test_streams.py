import asyncio
import json
import os
import sys
import time
import unittest
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))

import nats
from data import REGIONS, decode, orders

UI = os.environ.get("UI_URL", "http://localhost:8080")
SERVERS = os.environ.get("NATS_URLS", "nats://localhost:27301").split(",")


def get(path):
    with urllib.request.urlopen(f"{UI}{path}", timeout=60) as r:
        return r.read().decode()


def post(path):
    with urllib.request.urlopen(urllib.request.Request(f"{UI}{path}", method="POST"), timeout=60) as r:
        return json.load(r)


def ids(rows):
    return [r["id"] for r in rows]


async def read_stream(stream):
    nc = await nats.connect(servers=SERVERS)
    try:
        js = nc.jetstream(timeout=20)
        s = (await js.stream_info(stream)).state
        out = []
        for seq in range(s.first_seq, s.last_seq + 1):
            m = await js.get_msg(stream, seq)
            out.append((m.subject, decode(m.data)))
        return out
    finally:
        await nc.close()


class JetStreamBehaviour(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = json.loads(get("/api/results"))
        for name in ["retention", "consumers", "replay", "kv"]:
            assert name in cls.r, f"scenario {name} has no result, run POST /api/run-all first"

    def test_limits_stream_keeps_only_the_newest_max_msgs_and_drops_the_oldest(self):
        limits = self.r["retention"]["limits"]
        expected = ids(orders(80))[-50:]
        self.assertEqual(limits["messages"], 50)
        self.assertEqual(limits["kept_ids"], expected, "discard old must evict the oldest 30 orders, not the newest")
        self.assertEqual((limits["first_seq"], limits["last_seq"]), (31, 80))

    def test_limits_stream_bytes_are_the_published_orders(self):
        stored = asyncio.run(read_stream("RET_LIMITS"))
        self.assertEqual([row for _, row in stored], orders(80)[-50:], "stored payloads read directly from nats must equal the generated input")

    def test_workqueue_removes_acked_jobs_and_keeps_only_unprocessed_ones(self):
        work = self.r["retention"]["workqueue"]
        jobs = ids(orders(20))
        self.assertEqual(work["acked_ids"], jobs[:12], "a work queue hands out jobs in publish order")
        self.assertEqual(work["left_ids"], [j for j in jobs if j not in work["acked_ids"]])
        self.assertEqual(work["messages"], 20 - 12)
        self.assertTrue(work["second_consumer"].startswith("rejected"), "a work queue must not let two consumers process the same job")

    def test_interest_stream_keeps_a_message_until_every_consumer_acked_it(self):
        interest = self.r["retention"]["interest"]
        published = ids(orders(10))
        acked_by_all = set(interest["audit_acked_ids"]) & set(published[: interest["email_acked"]])
        self.assertEqual(interest["left_ids"], [i for i in published if i not in acked_by_all])
        self.assertEqual(interest["messages"], 10 - len(acked_by_all))

    def test_nak_redelivers_at_once_and_a_missing_ack_redelivers_after_ack_wait(self):
        c = self.r["consumers"]
        first = {e["id"]: e for e in c["log"] if e["delivered"] == 1}
        second = {e["id"]: e for e in c["log"] if e["delivered"] == 2}
        self.assertEqual(sorted(first), ids(orders(10)))
        self.assertEqual(sorted(second), [8, 9], "only the nak and the unacked order come back, acked and terminated ones never do")
        self.assertLess(second[8]["ms"] - first[8]["ms"], 1000, "nak must redeliver without waiting for ack_wait")
        self.assertGreaterEqual(second[9]["ms"] - first[9]["ms"], 1900, "an unacked message must wait for the 2 s ack_wait")
        self.assertNotIn(10, second)

    def test_durable_consumer_resumes_after_reconnect_with_only_new_messages(self):
        c = self.r["consumers"]
        self.assertEqual(c["resumed_ids"], ids(orders(2, start=11)), "the durable keeps its position on the server, so a new connection gets only 11 and 12")
        self.assertEqual(c["billing"]["ack_floor_stream_seq"], c["published"])
        self.assertEqual(c["billing"]["num_ack_pending"], 0)
        self.assertEqual(c["billing"]["num_pending"], 0)

    def test_max_deliver_stops_redelivering_a_poison_message(self):
        p = self.r["consumers"]["poison"]
        self.assertEqual(p["attempts"], list(range(1, p["max_deliver"] + 1)))

    def test_orders_stream_routes_each_order_to_its_region_subject(self):
        stored = asyncio.run(read_stream("ORDERS"))
        generated = orders(10) + orders(2, start=11)
        self.assertEqual([(s, row) for s, row in stored if row["id"] != 99], [(f"orders.{o['region']}", o) for o in generated])

    def test_replay_from_sequence_and_from_time(self):
        r = self.r["replay"]
        all_ids = ids(orders(30))
        self.assertEqual(r["all"], all_ids)
        self.assertEqual(r["from_seq_21"], all_ids[20:])
        self.assertEqual(r["from_time_batch2"], all_ids[10:], "start time between batch 1 and 2 must skip exactly batch 1")

    def test_last_per_subject_is_the_last_order_of_each_region(self):
        expected = {}
        for o in orders(30):
            expected[f"events.{o['region']}"] = o["id"]
        self.assertEqual(self.r["replay"]["last_per_subject"], expected)
        self.assertLessEqual(set(expected), {f"events.{g}" for g in REGIONS})

    def test_original_replay_keeps_the_publish_gap(self):
        pace = self.r["replay"]["original_pace"]
        self.assertEqual(pace["ids"], ids(orders(30))[9:])
        self.assertGreaterEqual(pace["gap_between_seq10_and_seq11_ms"], 1000, "batch 2 was published 1.4 s after batch 1, original replay must wait that long")
        self.assertLess(pace["instant_gap_ms"], 300, "instant replay must not wait")

    def test_get_message_by_sequence(self):
        o = orders(30)[14]
        self.assertEqual(self.r["replay"]["get_msg_seq_15"], {"subject": f"events.{o['region']}", "id": o["id"]})

    def test_kv_keeps_history_and_enforces_compare_and_set(self):
        kv = self.r["kv"]
        self.assertEqual(kv["current"], {"revision": len(kv["puts"]), "value": kv["puts"][-1]})
        self.assertEqual([h["value"] for h in kv["history"]], kv["puts"][-kv["history_limit"]:], "history=5 keeps only the last 5 values")
        self.assertTrue(kv["stale_update"].startswith("rejected"), "an update with an old revision must fail")
        self.assertEqual(kv["cas_update_revision"], kv["current"]["revision"] + 1)
        self.assertTrue(kv["duplicate_create"].startswith("rejected"), "create must fail when the key exists")
        self.assertIn("op=DEL", kv["after_delete"])
        self.assertEqual(kv["keys"], ["feature.checkout"])

    def test_kv_watch_sees_every_change_in_order(self):
        kv = self.r["kv"]
        expected = [("feature.checkout", "PUT", v) for v in kv["puts"] + ["v8"]] + [("feature.search", "PUT", "on"), ("feature.search", "DEL", None)]
        watched = kv["watched"]
        self.assertEqual([(w["key"], w["op"], w["value"]) for w in watched], expected)
        self.assertEqual([w["revision"] for w in watched], list(range(1, len(expected) + 1)))

    def test_every_stream_has_a_leader_and_two_current_replicas_on_distinct_nodes(self):
        deadline = time.monotonic() + 20
        while True:
            cluster = json.loads(get("/api/cluster"))
            ok = all(s["leader"] and len(s["replicas"]) == 2 and all(p["current"] for p in s["replicas"]) for s in cluster["streams"])
            if ok or time.monotonic() > deadline:
                break
            time.sleep(1)
        self.assertEqual({n["name"] for n in cluster["nodes"] if n["up"]}, {"n1", "n2", "n3"})
        for s in cluster["streams"]:
            placed = [s["leader"]] + [p["name"] for p in s["replicas"]]
            self.assertEqual(sorted(placed), ["n1", "n2", "n3"], f"{s['stream']} must live on all 3 nodes")
            self.assertTrue(all(p["current"] for p in s["replicas"]), f"{s['stream']} has a lagging replica")
            seqs = {n["name"]: n["streams"][s["stream"]]["last_seq"] for n in cluster["nodes"]}
            self.assertEqual(set(seqs.values()), {s["last_seq"]}, f"{s['stream']} replicas disagree: {seqs}")

    def test_leader_stepdown_elects_a_new_leader_and_writes_continue(self):
        r = post("/api/stepdown")
        self.assertNotEqual(r["new_leader"], r["old_leader"])
        self.assertIn(r["new_leader"], {"n1", "n2", "n3"})
        self.assertGreater(r["publish_after_stepdown_seq"], 0)

    def test_ui_page_has_every_tab(self):
        page = get("/")
        for tab in ["Retention", "Consumers", "Replay", "Key-Value", "Cluster"]:
            self.assertIn(f">{tab}<", page)


if __name__ == "__main__":
    unittest.main()
