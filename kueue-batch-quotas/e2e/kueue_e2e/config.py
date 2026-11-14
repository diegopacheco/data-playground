import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
JOB_TEMPLATE = ROOT / "k8s" / "etl-job.yaml"
KUBE_CONTEXT = os.environ.get("KUBE_CONTEXT", "kind-kueue-batch-quotas")
RESULTS_DIR = Path(os.environ.get("RESULTS_DIR", str(ROOT / ".run" / "results")))
REPORT_DIR = Path(os.environ.get("REPORT_DIR", str(ROOT / ".run")))
IMAGES = {
    "python": os.environ.get("PY_IMAGE", "localhost/kueue-batch-quotas-python:v1"),
    "java": os.environ.get("JAVA_IMAGE", "localhost/kueue-batch-quotas-java:v1"),
}
TEAMS = {
    "analytics": ("team-analytics", "analytics-cq"),
    "finance": ("team-finance", "finance-cq"),
    "reports": ("team-reports", "reports-cq"),
}
JOB_CPU_MILLI = 250
NOMINAL_CPU_MILLI = 500
SLOTS_PER_TEAM = NOMINAL_CPU_MILLI // JOB_CPU_MILLI
ROWS = int(os.environ.get("ETL_ROWS", "20000"))
ROUNDS = int(os.environ.get("ETL_ROUNDS", "3000"))
SEEDS = (0, 1, 2)
POLL_SECONDS = 0.5
SCENARIO_TIMEOUT_SECONDS = 600
