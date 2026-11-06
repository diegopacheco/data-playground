import json
import os
import ssl
import subprocess
import time
import unittest
import urllib.request
import uuid

URL = os.environ["ORDERS_URL"]
CONTEXT = os.environ["KUBE_CONTEXT"]
PIPELINE = os.environ["PIPELINE"]
INSECURE = ssl._create_unverified_context()


def post(body):
    req = urllib.request.Request(URL, data=body, method="POST",
                                 headers={"X-Numaflow-Id": uuid.uuid4().hex})
    with urllib.request.urlopen(req, context=INSECURE, timeout=10) as resp:
        return resp.status


def vertex_logs(vertex, container):
    return subprocess.run(
        ["kubectl", "--context", CONTEXT, "logs", "--tail=-1", "-c", container, "-l",
         f"numaflow.numaproj.io/pipeline-name={PIPELINE},numaflow.numaproj.io/vertex-name={vertex}"],
        capture_output=True, text=True, check=True).stdout


def sunk_ids(vertex):
    ids = set()
    for line in vertex_logs(vertex, "udsink").splitlines():
        if line.startswith('{"sink"'):
            ids.add(json.loads(line)["sink"]["id"])
    return ids


class PipelineTest(unittest.TestCase):
    def test_orders_are_routed_by_tier_and_bad_ones_never_reach_a_sink(self):
        run = uuid.uuid4().hex[:8]
        big = [f"{run}-big-{i}" for i in range(5)]
        small = [f"{run}-small-{i}" for i in range(5)]
        bad = f"{run}-bad"
        for oid in big:
            self.assertEqual(post(json.dumps({"id": oid, "qty": 2, "price_cents": 7500}).encode()), 200)
        for oid in small:
            self.assertEqual(post(json.dumps({"id": oid, "qty": 1, "price_cents": 99}).encode()), 200)
        self.assertEqual(post(json.dumps({"id": bad, "qty": 0, "price_cents": 1}).encode()), 200)

        expected = set(big) | set(small)
        for _ in range(60):
            in_big, in_small = sunk_ids("big"), sunk_ids("small")
            if expected <= in_big | in_small:
                break
            time.sleep(1)

        self.assertEqual(set(big), {i for i in in_big if i.startswith(run)})
        self.assertEqual(set(small), {i for i in in_small if i.startswith(run)})
        self.assertIn(bad, vertex_logs("enrich", "udf"))


if __name__ == "__main__":
    unittest.main()
