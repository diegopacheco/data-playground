import json
import subprocess
import time

from coldstart import config


def run(*args: str) -> str:
    done = subprocess.run(args, capture_output=True, text=True)
    if done.returncode != 0:
        raise RuntimeError(f"{' '.join(args)} failed: {done.stderr}")
    return done.stdout


def kubectl(*args: str) -> str:
    return run("kubectl", "--context", config.KUBE_CONTEXT, *args)


def pod_names(variant: str) -> list[str]:
    pods = json.loads(kubectl("get", "pods", "-l", f"serving.knative.dev/service=orders-{variant}", "-o", "json"))
    return [p["metadata"]["name"] for p in pods["items"]]


def wait_for_zero(variant: str, timeout_s: float = config.ZERO_TIMEOUT_S) -> float:
    start = time.monotonic()
    while time.monotonic() - start < timeout_s:
        if not pod_names(variant):
            return time.monotonic() - start
        time.sleep(1)
    raise TimeoutError(f"orders-{variant} did not scale to zero in {timeout_s}s")


def image_size_mb(variant: str) -> float:
    size = run("podman", "image", "inspect", "--format", "{{.Size}}", f"{config.IMAGE_PREFIX}-{variant}:v1")
    return int(size.strip()) / 1_000_000
