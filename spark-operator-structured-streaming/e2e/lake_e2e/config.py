import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
KUBE_CONTEXT = os.environ.get("KUBE_CONTEXT", "kind-spark-operator-structured-streaming")
RESULTS = Path(os.environ.get("RESULTS_FILE", str(ROOT / ".run" / "results.tsv")))
MANIFESTS = {"java": ROOT / "k8s" / "events-java.yaml", "python": ROOT / "k8s" / "events-python.yaml"}
LANGS = ("java", "python")
TOPIC = "events"
RATE = 50
WAIT_SECONDS = 300
WARMUP_SECONDS = 20
WINDOW_SECONDS = 90
TRIGGERS = (1, 5, 15, 30)
