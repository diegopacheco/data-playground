from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class EtlConfig:
    job_name: str
    pod_name: str
    team: str
    rows: int
    seed: int
    rounds: int
    results_dir: Path

    @staticmethod
    def from_env(env: Mapping[str, str]) -> "EtlConfig":
        cfg = EtlConfig(
            job_name=env["JOB_NAME"],
            pod_name=env["POD_NAME"],
            team=env["TEAM"],
            rows=int(env["ETL_ROWS"]),
            seed=int(env["ETL_SEED"]),
            rounds=int(env["ETL_ROUNDS"]),
            results_dir=Path(env.get("RESULTS_DIR", "/results")),
        )
        if cfg.rows < 1 or cfg.rounds < 1 or cfg.seed < 0:
            raise ValueError("ETL_ROWS and ETL_ROUNDS must be >= 1 and ETL_SEED >= 0")
        return cfg
