from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    endpoint: str
    access_key: str
    secret_key: str
    bucket: str
    poll_seconds: float
    parallel_batches: int

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> "Settings":
        settings = cls(
            endpoint=env.get("S3_ENDPOINT", "minio:9000"),
            access_key=env.get("S3_ACCESS_KEY", "minioadmin"),
            secret_key=env.get("S3_SECRET_KEY", "minioadmin"),
            bucket=env.get("S3_BUCKET", "events"),
            poll_seconds=float(env.get("POLL_SECONDS", "1")),
            parallel_batches=int(env.get("PARALLEL_BATCHES", "4")),
        )
        if settings.parallel_batches < 1 or settings.poll_seconds <= 0:
            raise ValueError("PARALLEL_BATCHES must be >= 1 and POLL_SECONDS > 0")
        return settings
