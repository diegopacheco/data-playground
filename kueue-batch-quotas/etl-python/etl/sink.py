import json
import os
from pathlib import Path

from etl.config import EtlConfig
from etl.transform import Summary


def job_dir(cfg: EtlConfig) -> Path:
    path = cfg.results_dir / cfg.job_name
    path.mkdir(parents=True, exist_ok=True)
    return path


def mark_started(cfg: EtlConfig, started_at_ms: int) -> Path:
    marker = job_dir(cfg) / f"{cfg.pod_name}.started"
    marker.write_text(str(started_at_ms))
    return marker


def result_row(cfg: EtlConfig, summary: Summary, worker: str, started_at_ms: int, finished_at_ms: int) -> dict[str, object]:
    return {
        "job": cfg.job_name,
        "team": cfg.team,
        "worker": worker,
        "pod": cfg.pod_name,
        "rows": summary.rows,
        "seed": cfg.seed,
        "rounds": cfg.rounds,
        "digest": summary.digest,
        "totals": summary.totals,
        "started_at_ms": started_at_ms,
        "finished_at_ms": finished_at_ms,
    }


def write_result(cfg: EtlConfig, row: dict[str, object]) -> Path:
    target = job_dir(cfg) / f"{cfg.pod_name}.json"
    tmp = target.with_suffix(".tmp")
    tmp.write_text(json.dumps(row, separators=(",", ":")))
    os.replace(tmp, target)
    return target
