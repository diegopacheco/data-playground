import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
KUBE_CONTEXT = os.environ.get("KUBE_CONTEXT", "kind-kuberay-ray-data-etl")
RESULTS = Path(os.environ.get("RESULTS_FILE", str(ROOT / ".run" / "results.md")))
BURST_MANIFEST = ROOT / "k8s" / "producer-burst.yaml"
BUCKET = "events"
ACCESS_KEY = "minioadmin"
SECRET_KEY = "minioadmin"
CLUSTER = "etl"
RAY_JOB = "etl-driver"
HEAD_SERVICE = "etl-head-svc:8265"
MIN_WORKERS = 1
MAX_WORKERS = 3
IDLE_TIMEOUT_SECONDS = 30
WAIT_SECONDS = 300


def port(name: str) -> int:
    for line in (ROOT / "scripts" / "ports.env").read_text().splitlines():
        key, _, value = line.partition("=")
        if key == name:
            return int(value)
    raise KeyError(f"{name} missing from scripts/ports.env")


S3_ENDPOINT = f"localhost:{port('minio-api')}"
