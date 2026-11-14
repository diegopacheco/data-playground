import json
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from typing import Any

from etl.transform import Summary, summarize
from kueue_e2e import config


@dataclass(frozen=True)
class Attempts:
    started: list[str]
    results: list[dict[str, Any]]


def attempts(job: str) -> Attempts:
    folder = config.RESULTS_DIR / job
    if not folder.is_dir():
        return Attempts([], [])
    started = sorted(p.stem for p in folder.glob("*.started"))
    results = [json.loads(p.read_text()) for p in sorted(folder.glob("*.json"))]
    return Attempts(started, results)


def summarize_seed(seed: int) -> Summary:
    return summarize(config.ROWS, seed, config.ROUNDS)


def expected_by_seed() -> dict[int, Summary]:
    with ProcessPoolExecutor(max_workers=len(config.SEEDS)) as pool:
        return dict(zip(config.SEEDS, pool.map(summarize_seed, config.SEEDS)))
