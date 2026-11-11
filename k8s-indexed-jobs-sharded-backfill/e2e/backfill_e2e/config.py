import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
JOB_TEMPLATE = ROOT / "k8s" / "backfill-job.yaml"
KUBE_CONTEXT = os.environ.get("KUBE_CONTEXT", "kind-k8s-indexed-jobs-sharded-backfill")
PG_PORT = int(os.environ.get("PG_PORT", "27600"))
PARTITIONS = 12
PARALLELISM = 4
SUBRANGES = 4
START_DAY = "2026-10-01"
IMAGES = {
    "python": os.environ.get("PY_IMAGE", "localhost/k8s-indexed-jobs-sharded-backfill-python:v1"),
    "java": os.environ.get("JAVA_IMAGE", "localhost/k8s-indexed-jobs-sharded-backfill-java:v1"),
}
WORKERS = tuple(IMAGES)
JOB_TIMEOUT_SECONDS = 600
