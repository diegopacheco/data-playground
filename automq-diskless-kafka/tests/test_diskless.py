import json
import os
import unittest
import urllib.request
from collections import Counter
from pathlib import Path
import s3
import streams

DATA_FILE = Path(os.environ.get("DATA_FILE", "/data/orders.jsonl"))
PROOF = Path(os.environ.get("PROOF", "/app/results/proof.json"))
UI = os.environ.get("UI_URL", "http://localhost:8080")
TOPIC = os.environ.get("TOPIC", "orders")
DATA_BUCKET = os.environ.get("DATA_BUCKET", "r9-automq-data")
STEPS = ["produce", "local-disk", "recreate-broker", "restart-controller", "consume"]


def get(path):
    with urllib.request.urlopen(f"{UI}{path}", timeout=30) as response:
        return json.loads(response.read())


class DisklessKafka(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.input = [line.encode() for line in DATA_FILE.read_text().splitlines() if line]
        cls.input_bytes = sum(len(line) for line in cls.input)
        cls.revenue_by_region = Counter()
        for line in cls.input:
            order = json.loads(line)
            cls.revenue_by_region[order["region"]] += order["quantity"] * order["price_cents"]
        cls.proof = json.loads(PROOF.read_text())
        cls.events = {e["step"]: e for e in cls.proof["events"]}
        cls.live = streams.consume(TOPIC)

    def test_proof_ran_every_step_in_order(self):
        self.assertEqual([e["step"] for e in self.proof["events"]], STEPS, "the consume must come after the broker replacement and the controller restart, or it proves nothing")

    def test_live_consume_returns_exactly_the_input_file(self):
        self.assertEqual(self.live["records"], len(self.input))
        self.assertEqual(sorted(self.live["values"]), sorted(self.input), "a record was lost, duplicated or changed after the brokers were replaced")

    def test_revenue_recomputed_from_consumed_records_matches_the_input(self):
        consumed = Counter()
        for value in self.live["values"]:
            order = json.loads(value)
            consumed[order["region"]] += order["quantity"] * order["price_cents"]
        self.assertEqual(consumed, self.revenue_by_region)

    def test_app_consume_after_restarts_matched_the_input(self):
        consumed = self.proof["consumed"]
        self.assertTrue(consumed["matches_input"])
        self.assertEqual((consumed["records"], consumed["missing"], consumed["duplicates"]), (len(self.input), 0, 0))
        self.assertEqual(consumed["sha256"], streams.fingerprint(self.input))

    def test_acked_bytes_landed_in_object_storage(self):
        written = self.proof["produced"]["s3_written"]
        self.assertGreater(written["wal_objects"], 0, "acks=all returned but no WAL object was written to S3")
        self.assertGreaterEqual(written["bytes"], self.input_bytes, "S3 received fewer bytes than the payload, so the data must live somewhere else")

    def test_brokers_keep_no_partition_data_on_local_disk(self):
        for node in self.events["local-disk"]["detail"]["nodes"]:
            self.assertEqual(node["orders_partition_bytes"], 0, f"{node['container']} stores orders partition bytes locally")
            self.assertEqual(node["orders_segment_files"], 0)
            self.assertFalse([f for f in node["files"] if f["path"].startswith(f"{TOPIC}-")], f"{node['container']} has local {TOPIC} partition files")

    def test_replaced_broker_is_a_new_container_that_starts_empty(self):
        detail = self.events["recreate-broker"]["detail"]
        self.assertNotEqual(detail["old_container"], detail["new_container"])
        self.assertEqual(detail["new_container_disk"]["orders_partition_bytes"], 0)
        self.assertLessEqual(detail["seconds_to_serve"], 60)

    def test_every_partition_has_a_live_leader_after_the_restarts(self):
        cluster = get("/api/cluster")
        self.assertEqual({b["id"] for b in cluster["brokers"]}, {0, 1})
        partitions = next(t for t in cluster["topics"] if t["name"] == TOPIC)["partitions"]
        self.assertEqual(len(partitions), streams.PARTITIONS)
        self.assertTrue(all(p["leader"] in (0, 1) for p in partitions))

    def test_bucket_objects_belong_to_this_kafka_cluster(self):
        cluster_id = get("/api/cluster")["cluster_id"]
        ours = [o for o in s3.list_objects(DATA_BUCKET) if f"_kafka_{cluster_id}/" in o["key"]]
        self.assertTrue(ours, "no object in the data bucket is keyed by this cluster id")
        self.assertGreaterEqual(sum(o["size"] for o in ours), self.input_bytes, "the cluster's objects are smaller than the data it serves")

    def test_ui_page_has_every_tab(self):
        with urllib.request.urlopen(f"{UI}/", timeout=10) as response:
            page = response.read().decode()
        for tab in ["Proof", "Object storage", "Cluster"]:
            self.assertIn(tab, page)


if __name__ == "__main__":
    unittest.main()
