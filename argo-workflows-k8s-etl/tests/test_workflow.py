import json
import os
import subprocess
import time
import unittest
from tests import expected
import argo
import data

BIG_CENTS = 75000
TIMEOUT = 300


def psql(sql):
    cmd = ["kubectl", "--context", os.environ["KUBE_CONTEXT"], "-n", os.environ["NAMESPACE"], "exec", "deployment/t8-postgres",
           "--", "psql", "-U", "etl", "-d", "etl", "-At", "-F", "|", "-c", sql]
    out = subprocess.run(cmd, check=True, capture_output=True, text=True).stdout
    return [line.split("|") for line in out.splitlines() if line]


def wait(client, name):
    deadline = time.time() + TIMEOUT
    while time.time() < deadline:
        wf = client.workflow(name)
        phase = (wf.get("status") or {}).get("phase")
        if phase in ("Succeeded", "Failed", "Error"):
            return wf
        time.sleep(2)
    raise AssertionError(f"{name} did not finish in {TIMEOUT}s")


def by_template(wf, template):
    return [s for s in argo.steps(wf) if s["template"] == template]


class WorkflowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.argo = argo.Argo(os.environ["ARGO_URL"], os.environ["NAMESPACE"])
        cls.want_hot = expected.region_totals(11, 800, BIG_CENTS)
        ordered = sorted(t["cents"] for t in cls.want_hot.values())
        cls.threshold = ordered[len(ordered) // 2]
        cls.want_cold = expected.region_totals(12, 500, BIG_CENTS)
        cls.cold_threshold = max(t["cents"] for t in cls.want_cold.values())
        hot = cls.argo.submit("WorkflowTemplate", argo.TEMPLATE, {"seed": 11, "rows": 800, "alert_cents": cls.threshold, "big_cents": BIG_CENTS})
        cold = cls.argo.submit("WorkflowTemplate", argo.TEMPLATE, {"seed": 12, "rows": 500, "alert_cents": cls.cold_threshold, "big_cents": BIG_CENTS})
        cron = cls.argo.submit("CronWorkflow", argo.CRON, {})
        cls.hot, cls.cold, cls.cron_run = (wait(cls.argo, n) for n in (hot, cold, cron))

    def loaded(self, wf):
        name = wf["metadata"]["name"]
        rows = psql(f"SELECT region, orders, cents, max_cents, big_orders, days FROM region_totals WHERE batch = '{name}'")
        return {r[0]: {"orders": int(r[1]), "cents": int(r[2]), "max_cents": int(r[3]), "big_orders": int(r[4]), "days": int(r[5])} for r in rows}

    def test_every_run_succeeds(self):
        for wf in (self.hot, self.cold, self.cron_run):
            self.assertEqual(wf["status"]["phase"], "Succeeded", wf["metadata"]["name"])

    def test_loaded_totals_match_independent_computation(self):
        self.assertEqual(self.loaded(self.hot), self.want_hot)
        self.assertEqual(self.loaded(self.cold), self.want_cold)
        name = self.hot["metadata"]["name"]
        batch = psql(f"SELECT seed, rows, orders, cents FROM batches WHERE batch = '{name}'")
        self.assertEqual(batch, [["11", "800", "800", str(sum(o["cents"] for o in data.orders(11, 800)))]])

    def test_extract_artifact_in_minio_is_the_seeded_input(self):
        extract = by_template(self.hot, "extract")[0]
        raw = self.argo.artifact(self.hot["metadata"]["name"], extract["id"], "orders").decode()
        self.assertEqual([json.loads(line) for line in raw.splitlines()], data.orders(11, 800))
        self.assertEqual(json.loads(extract["outputs"]["regions"]), sorted(self.want_hot))

    def test_fan_out_one_transform_per_region_and_fan_in_after_all(self):
        transforms = by_template(self.hot, "transform")
        self.assertEqual(sorted(t["name"].split(":")[1].rstrip(")") for t in transforms), sorted(self.want_hot))
        merge = by_template(self.hot, "merge")[0]
        self.assertGreaterEqual(merge["started"], max(t["finished"] for t in transforms))
        self.assertEqual(int(merge["outputs"]["total_cents"]), sum(t["cents"] for t in self.want_hot.values()))

    def test_flaky_region_failed_once_then_retried(self):
        for t in by_template(self.hot, "transform"):
            phases = [a["phase"] for a in t["attempts"]]
            if t["name"].endswith(":br)"):
                self.assertEqual(phases, ["Failed", "Succeeded"], t)
                self.assertIn("exit code 3", t["attempts"][0]["message"])
            else:
                self.assertEqual(phases, ["Succeeded"], t)
            self.assertEqual(t["phase"], "Succeeded")

    def test_alert_runs_when_a_region_is_above_threshold(self):
        alert = by_template(self.hot, "alert")[0]
        self.assertEqual(alert["phase"], "Succeeded")
        name = self.hot["metadata"]["name"]
        got = sorted(r[0] for r in psql(f"SELECT region FROM alerts WHERE batch = '{name}'"))
        want = sorted(r for r, t in self.want_hot.items() if t["cents"] > self.threshold)
        self.assertEqual(got, want)
        self.assertTrue(0 < len(want) < len(self.want_hot))

    def test_alert_is_skipped_when_no_region_is_above_threshold(self):
        alert = by_template(self.cold, "alert")[0]
        self.assertEqual(alert["phase"], "Skipped")
        self.assertIn("evaluated false", alert["message"])
        name = self.cold["metadata"]["name"]
        self.assertEqual(psql(f"SELECT region FROM alerts WHERE batch = '{name}'"), [])

    def test_cron_workflow_schedule_and_submitted_run(self):
        cron = self.argo.cron()
        self.assertEqual(cron["spec"]["schedules"], ["*/5 * * * *"])
        self.assertEqual(cron["spec"]["concurrencyPolicy"], "Forbid")
        self.assertEqual(self.cron_run["metadata"]["labels"].get("workflows.argoproj.io/cron-workflow"), argo.CRON)
        self.assertEqual(self.loaded(self.cron_run), expected.region_totals(21, 600, BIG_CENTS))


if __name__ == "__main__":
    unittest.main()
