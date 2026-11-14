import json
import subprocess
from typing import Any

from kueue_e2e import config


def kubectl(*args: str, stdin: str | None = None) -> str:
    done = subprocess.run(
        ["kubectl", "--context", config.KUBE_CONTEXT, *args],
        input=stdin,
        capture_output=True,
        text=True,
    )
    if done.returncode != 0:
        raise RuntimeError(f"kubectl {' '.join(args)} failed: {done.stderr}")
    return done.stdout


def items(*args: str) -> list[dict[str, Any]]:
    return json.loads(kubectl("get", *args, "-o", "json"))["items"]


def get(*args: str) -> dict[str, Any]:
    return json.loads(kubectl("get", *args, "-o", "json"))


def cpu_milli(quantity: str) -> int:
    if quantity.endswith("m"):
        return int(quantity[:-1])
    return int(float(quantity) * 1000)
