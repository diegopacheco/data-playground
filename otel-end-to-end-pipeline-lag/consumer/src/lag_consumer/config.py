import os
from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    bootstrap: str
    topic: str
    group: str
    pg_host: str
    pg_database: str
    pg_user: str
    pg_password: str
    slowdown_ms: int


def load(env: Mapping[str, str] = os.environ) -> Settings:
    slowdown_ms = int(env.get("SLOWDOWN_MS", "0"))
    if slowdown_ms < 0:
        raise ValueError("SLOWDOWN_MS must be >= 0")
    return Settings(
        bootstrap=env.get("KAFKA_BOOTSTRAP", "localhost:9092"),
        topic=env.get("TOPIC", "orders"),
        group=env.get("GROUP", "lag-consumer"),
        pg_host=env.get("PG_HOST", "localhost"),
        pg_database=env.get("PG_DATABASE", "pipeline"),
        pg_user=env.get("PG_USER", "pipeline"),
        pg_password=env["PG_PASSWORD"],
        slowdown_ms=slowdown_ms,
    )
