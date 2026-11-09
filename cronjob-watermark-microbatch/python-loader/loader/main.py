import os
import signal
import sys

import psycopg

from loader import batch
from loader.config import settings_from_env
from loader.generator import generate_forever, generator_settings_from_env


def load() -> None:
    settings = settings_from_env(os.environ)
    with psycopg.connect(settings.conninfo, autocommit=True) as conn:
        summary = batch.run(conn, settings)
    print(
        f"job={settings.job} runner={settings.runner} rows={summary.rows} pages={summary.pages} "
        f"duration_ms={summary.duration_ms} watermark={summary.watermark.updated_at.isoformat()}/{summary.watermark.id}",
        flush=True,
    )


def main(argv: list[str]) -> None:
    signal.signal(signal.SIGTERM, lambda signum, frame: sys.exit(143))
    command = argv[1] if len(argv) > 1 else "load"
    if command == "load":
        load()
    elif command == "generate":
        generate_forever(generator_settings_from_env(os.environ))
    else:
        raise SystemExit(f"unknown command {command}, use load or generate")


if __name__ == "__main__":
    main(sys.argv)
