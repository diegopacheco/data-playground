import json
from typing import Any

from lake_e2e import config

HEADER = "test\tlang\tparams\tresult"


def record(test: str, lang: str, params: str, result: dict[str, Any]) -> None:
    config.RESULTS.parent.mkdir(parents=True, exist_ok=True)
    fresh = not config.RESULTS.exists()
    with config.RESULTS.open("a") as out:
        if fresh:
            out.write(HEADER + "\n")
        out.write(f"{test}\t{lang}\t{params}\t{json.dumps(result, separators=(',', ':'))}\n")


def reset() -> None:
    config.RESULTS.unlink(missing_ok=True)
