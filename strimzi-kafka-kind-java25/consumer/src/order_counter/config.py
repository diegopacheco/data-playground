import os
from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    bootstrap: str
    user: str
    password: str
    topic: str
    group: str


def load(env: Mapping[str, str] = os.environ) -> Settings:
    missing = [name for name in ("KAFKA_BOOTSTRAP", "KAFKA_USER", "KAFKA_PASSWORD") if not env.get(name)]
    if missing:
        raise ValueError(f"missing environment variables: {', '.join(missing)}")
    return Settings(
        bootstrap=env["KAFKA_BOOTSTRAP"],
        user=env["KAFKA_USER"],
        password=env["KAFKA_PASSWORD"],
        topic=env.get("KAFKA_TOPIC", "orders"),
        group=env.get("KAFKA_GROUP", "order-counter"),
    )
