import json
import subprocess
import time
import unittest
import urllib.request
from pathlib import Path

PORTS = dict(line.strip().split("=") for line in (Path(__file__).resolve().parent.parent / "scripts" / "ports.env").read_text().splitlines() if "=" in line)
UI = f"http://localhost:{PORTS['ui']}"
MONITORS = {f"n{i}": f"http://localhost:{PORTS[f'monitor{i}']}" for i in (1, 2, 3)}
VICTIM = "r8-nats-3"


def call(url, method="GET"):
    with urllib.request.urlopen(urllib.request.Request(url, method=method), timeout=60) as r:
        return json.load(r)


def ledger_seq(node):
    jsz = call(f"{MONITORS[node]}/jsz?accounts=true&streams=true")
    for acc in jsz.get("account_details") or []:
        for s in acc.get("stream_detail") or []:
            if s["name"] == "LEDGER":
                return s["state"]["last_seq"]
    return None


def publish(n):
    deadline = time.monotonic() + 30
    while True:
        try:
            return call(f"{UI}/api/ledger?n={n}", "POST")
        except Exception:
            if time.monotonic() > deadline:
                raise
            time.sleep(1)


def podman(*args):
    subprocess.run(["podman", *args], check=True, capture_output=True)


class NodeFailover(unittest.TestCase):
    def test_r3_stream_accepts_writes_with_a_node_down_and_the_node_catches_up(self):
        base = publish(10)
        start = base["last_seq_after"]
        podman("stop", "-t", "5", VICTIM)
        try:
            during = publish(100)
            self.assertEqual(during["acked"], 100, "with 2 of 3 nodes the stream still has quorum and must ack every write")
            self.assertEqual(during["last_seq_after"], start + 100)
            self.assertIsNone(next((r for r in during["placement"]["replicas"] if r["name"] == "n3" and r["current"]), None), "n3 is stopped so it cannot be a current replica")
        finally:
            podman("start", VICTIM)
        deadline = time.monotonic() + 60
        seqs = {}
        while time.monotonic() < deadline:
            try:
                seqs = {n: ledger_seq(n) for n in MONITORS}
            except Exception:
                seqs = {}
            if seqs and set(seqs.values()) == {start + 100}:
                break
            time.sleep(1)
        self.assertEqual(seqs, {n: start + 100 for n in MONITORS}, "the restarted node must catch up with the writes it missed")


if __name__ == "__main__":
    unittest.main()
