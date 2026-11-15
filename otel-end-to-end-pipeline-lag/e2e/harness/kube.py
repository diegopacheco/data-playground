import os
import subprocess

CONTEXT = os.environ.get("KUBE_CONTEXT", "kind-otel-end-to-end-pipeline-lag")
NAMESPACE = os.environ.get("PIPELINE_NAMESPACE", "pipeline")


def kubectl(*args: str) -> str:
    result = subprocess.run(
        ["kubectl", "--context", CONTEXT, "-n", NAMESPACE, *args], capture_output=True, text=True, timeout=300
    )
    if result.returncode != 0:
        raise RuntimeError(f"kubectl {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def psql(query: str) -> list[list[str]]:
    out = kubectl("exec", "deploy/postgres", "--", "psql", "-U", "pipeline", "-d", "pipeline", "-At", "-F", ",", "-c", query)
    return [line.split(",") for line in out.splitlines() if line]


def set_consumer_slowdown(ms: int) -> None:
    kubectl("set", "env", "deploy/lag-consumer", f"SLOWDOWN_MS={ms}")
    kubectl("rollout", "status", "deploy/lag-consumer", "--timeout=120s")
