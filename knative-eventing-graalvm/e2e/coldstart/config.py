import os
from pathlib import Path

KUBE_CONTEXT = os.environ.get("KUBE_CONTEXT", "kind-knative-eventing-graalvm")
LAB_URL = os.environ.get("LAB_URL", "http://localhost:27630")
IMAGE_PREFIX = os.environ.get("IMAGE_PREFIX", "kind.local/knative-eventing-graalvm")
RESULTS_DIR = Path(os.environ.get("RESULTS_DIR", Path(__file__).resolve().parents[2] / ".run"))
VARIANTS = ("native", "jvm", "jvm-aot", "python")
ZERO_TIMEOUT_S = 240
RECORD_TIMEOUT_S = 120
SETTLE_S = 3
WARM_EVENTS = 10
