import time
from collections.abc import Mapping
from dataclasses import dataclass

import psycopg

from loader.config import conninfo_from_env

INSERT_SQL = """
INSERT INTO source_events (account, amount_cents, updated_at)
SELECT 'acc-' || (random() * 50)::int, (random() * 10000)::bigint, now()
FROM generate_series(1, %s)
"""

UPDATE_SQL = """
UPDATE source_events SET amount_cents = amount_cents + 1, updated_at = now()
WHERE id IN (
  SELECT (random() * (SELECT coalesce(max(id), 0) FROM source_events))::bigint
  FROM generate_series(1, %s)
)
"""


@dataclass(frozen=True)
class GeneratorSettings:
    conninfo: str
    inserts_per_tick: int
    updates_per_tick: int
    tick_ms: int


def generator_settings_from_env(env: Mapping[str, str]) -> GeneratorSettings:
    return GeneratorSettings(
        conninfo=conninfo_from_env(env, "generator"),
        inserts_per_tick=int(env.get("INSERTS_PER_TICK", "20")),
        updates_per_tick=int(env.get("UPDATES_PER_TICK", "2")),
        tick_ms=int(env.get("TICK_MS", "500")),
    )


def generate_forever(settings: GeneratorSettings) -> None:
    with psycopg.connect(settings.conninfo, autocommit=True) as conn:
        while True:
            conn.execute(INSERT_SQL, (settings.inserts_per_tick,))
            conn.execute(UPDATE_SQL, (settings.updates_per_tick,))
            time.sleep(settings.tick_ms / 1000)
