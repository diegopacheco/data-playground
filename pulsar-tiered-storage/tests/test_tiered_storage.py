import csv
import json
import os
import re
import subprocess
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

UI = os.environ.get("UI_URL", "http://localhost:27200")
BROKER = os.environ.get("BROKER_URL", "http://localhost:27201")
BOOKIE = os.environ.get("BOOKIE_URL", "http://localhost:27202")
S3 = os.environ.get("S3_URL", "http://localhost:27203")
DATA = Path(os.environ.get("DATA_DIR", "data"), "readings.csv")
TOPIC = "persistent/public/default/readings"
BUCKET = "pulsar-offload"
PER_LEDGER = 120


def fetch(url, method="GET", raw=False, timeout=120):
    with urllib.request.urlopen(urllib.request.Request(url, method=method), timeout=timeout) as r:
        body = r.read()
    return body if raw else json.loads(body)


def eventually(check, tries=60):
    last = None
    for _ in range(tries):
        try:
            result = check()
            if result:
                return result
        except (urllib.error.URLError, ConnectionError, KeyError) as e:
            last = e
        time.sleep(1)
    raise AssertionError(f"condition not met after {tries}s, last error {last}")


def csv_lines():
    with DATA.open() as f:
        return [",".join(r) for r in list(csv.reader(f))[1:]]


def by_sensor(lines):
    out = {}
    for line in lines:
        _, sensor, value, _ = line.split(",")
        count, total = out.get(sensor, (0, 0))
        out[sensor] = (count + 1, total + int(value))
    return out


def internal_stats():
    return fetch(f"{BROKER}/admin/v2/{TOPIC}/internalStats")


def bookie_ledgers():
    return {int(k) for k in fetch(f"{BOOKIE}/api/v1/ledger/list/") or {}}


def s3_keys():
    xml = fetch(f"{S3}/{BUCKET}?list-type=2&max-keys=1000", raw=True).decode()
    return re.findall(r"<Key>([^<]+)</Key>", xml)


def entry(ledger, entry_id):
    return fetch(f"{BROKER}/admin/v2/{TOPIC}/ledger/{ledger}/entry/{entry_id}", raw=True).decode()


class TieredStorage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lines = csv_lines()
        fetch(f"{UI}/api/reset", "POST")
        published = fetch(f"{UI}/api/publish", "POST")
        assert published["published"] == len(cls.lines), published
        stats = internal_stats()
        cls.closed = [l["ledgerId"] for l in stats["ledgers"][:-1]]
        cls.open = stats["ledgers"][-1]["ledgerId"]

    def rows_of(self, index):
        return self.lines[index * PER_LEDGER:(index + 1) * PER_LEDGER]

    def test_1_publish_splits_the_topic_into_bookkeeper_ledgers(self):
        stats = internal_stats()
        closed = stats["ledgers"][:-1]
        self.assertEqual(len(closed), len(self.lines) // PER_LEDGER, "a closed ledger per 120 entries, the unit that can be offloaded")
        self.assertTrue(all(l["entries"] == PER_LEDGER for l in closed))
        self.assertEqual(stats["currentLedgerEntries"], len(self.lines) % PER_LEDGER, "the tail stays in the open ledger")
        self.assertEqual(stats["entriesAddedCounter"], len(self.lines))
        self.assertLessEqual({*self.closed, self.open}, bookie_ledgers(), "every ledger starts on the bookie")
        self.assertFalse(any(l.get("offloaded") for l in stats["ledgers"]))
        self.assertFalse([k for k in s3_keys() if any(k.endswith(f"-ledger-{lid}") for lid in self.closed)], "nothing in MinIO before offload")
        for i, lid in enumerate(self.closed):
            self.assertEqual(entry(lid, 0), self.rows_of(i)[0])
            self.assertEqual(entry(lid, PER_LEDGER - 1), self.rows_of(i)[-1])

    def test_2_offload_moves_every_closed_ledger_into_minio(self):
        fetch(f"{UI}/api/offload", "POST")
        status = eventually(lambda: (s := fetch(f"{BROKER}/admin/v2/{TOPIC}/offload")) and s["status"] != "RUNNING" and s)
        self.assertEqual(status["status"], "SUCCESS", status)
        self.assertEqual(status["firstUnoffloadedMessage"]["ledgerId"], self.open, "offload stops at the open ledger")
        ledgers = {l["ledgerId"]: l for l in internal_stats()["ledgers"]}
        self.assertTrue(all(ledgers[lid]["offloaded"] for lid in self.closed))
        self.assertFalse(ledgers[self.open].get("offloaded"))
        keys = s3_keys()
        for i, lid in enumerate(self.closed):
            data = [k for k in keys if k.endswith(f"-ledger-{lid}")]
            self.assertEqual(len(data), 1, f"one data block for ledger {lid}")
            self.assertIn(data[0] + "-index", keys)
            blob = fetch(f"{S3}/{BUCKET}/{data[0]}", raw=True)
            inside = [line for line in self.lines if line.encode() in blob]
            self.assertEqual(inside, self.rows_of(i), f"the S3 object of ledger {lid} holds exactly its 120 csv rows")
        self.assertFalse([k for k in keys if k.endswith(f"-ledger-{self.open}")])

    def test_3_bookie_drops_offloaded_ledgers_and_keeps_the_open_one(self):
        eventually(lambda: not set(self.closed) & bookie_ledgers())
        self.assertIn(self.open, bookie_ledgers())

    def test_4_read_back_from_tiered_storage_equals_the_csv(self):
        self.assertFalse(set(self.closed) & bookie_ledgers(), "reads below can only come from MinIO")
        result = fetch(f"{UI}/api/read")
        self.assertTrue(result["matches"])
        expected = by_sensor(self.lines)
        self.assertEqual(result["read"]["messages"], len(self.lines))
        self.assertEqual({k: (v["count"], v["valueMilliSum"]) for k, v in result["read"]["bySensor"].items()}, expected)
        served = {l["ledgerId"]: l["servedFrom"] for l in result["ledgers"]}
        self.assertTrue(all(served[lid].startswith("tiered storage") for lid in self.closed))
        self.assertEqual(served[self.open], "BookKeeper")
        for i, lid in enumerate(self.closed):
            self.assertEqual([entry(lid, e) for e in (0, 59, PER_LEDGER - 1)], [self.rows_of(i)[e] for e in (0, 59, PER_LEDGER - 1)])

    def test_5_broker_restart_loses_nothing_because_it_holds_no_data(self):
        mounts = subprocess.run(["podman", "inspect", "-f", "{{len .Mounts}}", "r7-broker"], capture_output=True, text=True, check=True).stdout.strip()
        self.assertEqual(mounts, "0", "the broker has no volume")
        subprocess.run(["podman", "restart", "r7-broker"], capture_output=True, check=True)
        eventually(lambda: fetch(f"{BROKER}/admin/v2/brokers/health", raw=True) == b"ok", 90)
        result = eventually(lambda: (r := fetch(f"{UI}/api/read")) and r["matches"] and r, 90)
        self.assertEqual(result["read"]["messages"], len(self.lines))
        ledgers = {l["ledgerId"]: l for l in internal_stats()["ledgers"]}
        self.assertTrue(all(ledgers[lid]["offloaded"] for lid in self.closed), "offload state lives in metadata, not in the broker")

    def test_6_broker_computes_bookie_stores(self):
        cluster = fetch(f"{UI}/api/cluster")
        self.assertEqual(cluster["brokers"], fetch(f"{BROKER}/admin/v2/brokers/r7-cluster"))
        self.assertEqual([b["bookieId"] for b in cluster["bookies"]], ["r7-bookie:3181"])
        self.assertEqual(cluster["topicOwner"]["brokerUrl"], "pulsar://r7-broker:6650")
        mounts = subprocess.run(["podman", "inspect", "-f", "{{range .Mounts}}{{.Name}}{{end}}", "r7-bookie"], capture_output=True, text=True, check=True).stdout.strip()
        self.assertEqual(mounts, "r7-bookie-data", "the bookie is the only pulsar node with a data volume")
        self.assertEqual(cluster["brokerConfig"]["managedLedgerMaxEntriesPerLedger"], str(PER_LEDGER))


if __name__ == "__main__":
    unittest.main()
