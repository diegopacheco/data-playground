import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
JOB_TEMPLATE = ROOT / "k8s" / "bench-job.yaml"
KUBE_CONTEXT = os.environ.get("KUBE_CONTEXT", "kind-apache-iggy-streaming")
RESULTS_DIR = Path(os.environ.get("RESULTS_DIR", str(ROOT / ".run")))
IMAGES = {
    "python": os.environ.get("PY_IMAGE", "localhost/apache-iggy-streaming-python:v1"),
    "java": os.environ.get("JAVA_IMAGE", "localhost/apache-iggy-streaming-java:v1"),
}
BROKERS = ("iggy", "kafka")
CLIENTS = tuple(IMAGES)
PARTITIONS = 3
WARMUP_SECONDS = 2
JOB_TIMEOUT_SECONDS = 300
