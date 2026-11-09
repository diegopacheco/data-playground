import re
from collections.abc import Mapping
from dataclasses import dataclass

from psycopg.conninfo import make_conninfo


@dataclass(frozen=True)
class Settings:
    job: str
    runner: str
    conninfo: str
    page_size: int
    lag_seconds: int
    hold_before_commit_ms: int

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[a-z]+", self.job):
            raise ValueError(f"JOB must be lowercase letters only, got {self.job!r}")
        if self.page_size <= 0:
            raise ValueError(f"PAGE_SIZE must be positive, got {self.page_size}")
        if self.lag_seconds < 0 or self.hold_before_commit_ms < 0:
            raise ValueError("LAG_SECONDS and HOLD_BEFORE_COMMIT_MS must not be negative")

    @property
    def target_table(self) -> str:
        return f"target_{self.job}"


def conninfo_from_env(env: Mapping[str, str], application_name: str) -> str:
    return make_conninfo(
        host=env.get("DB_HOST", "localhost"),
        port=env.get("DB_PORT", "27590"),
        dbname=env.get("DB_NAME", "microbatch"),
        user=env.get("DB_USER", "microbatch"),
        password=env.get("DB_PASSWORD", "microbatch"),
        application_name=application_name,
    )


def settings_from_env(env: Mapping[str, str]) -> Settings:
    job = env.get("JOB", "python")
    return Settings(
        job=job,
        runner=env.get("HOSTNAME", "local"),
        conninfo=conninfo_from_env(env, f"loader-{job}"),
        page_size=int(env.get("PAGE_SIZE", "500")),
        lag_seconds=int(env.get("LAG_SECONDS", "2")),
        hold_before_commit_ms=int(env.get("HOLD_BEFORE_COMMIT_MS", "0")),
    )
