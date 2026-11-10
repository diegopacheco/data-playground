import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
KUBE_CONTEXT = os.environ.get("KUBE_CONTEXT", "kind-flink-k8s-operator-savepoints")
RESULTS = Path(os.environ.get("RESULTS_FILE", str(ROOT / ".run" / "results.tsv")))
TAPS = ROOT / ".run" / "logs" / "taps"
MANIFESTS = {"java": ROOT / "k8s" / "clicks-java.yaml", "python": ROOT / "k8s" / "clicks-python.yaml"}
USERS = 10
WAIT_SECONDS = 300
