import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

from backfill.aggregate import merge_all, row_count
from backfill.partition import partition_for, split
from backfill.settings import Settings
from backfill.store import Attempt, TransientFailure, fetch_range, record_failure, write_partition

EXIT_TRANSIENT = 42
EXIT_FATAL = 3


def run(settings: Settings) -> int:
    partition = partition_for(settings.start_day, settings.index)
    attempt = Attempt(settings, partition, datetime.now(UTC))
    if settings.must_fail_fatally():
        record_failure(attempt, "fatal")
        print(f"index={settings.index} day={partition.day} fatal", flush=True)
        return EXIT_FATAL
    began = time.perf_counter()
    windows = split(partition.window, settings.sub_ranges)
    with ThreadPoolExecutor(max_workers=len(windows)) as pool:
        aggregates = merge_all(pool.map(fetch_range, windows))
    rows = row_count(aggregates)
    try:
        write_partition(attempt, aggregates, rows)
    except TransientFailure as failure:
        record_failure(attempt, "transient")
        print(f"index={settings.index} day={partition.day} {failure}", flush=True)
        return EXIT_TRANSIENT
    elapsed = time.perf_counter() - began
    print(f"index={settings.index} day={partition.day} rows={rows} categories={len(aggregates)} seconds={elapsed:.3f}", flush=True)
    return 0


def main() -> None:
    sys.exit(run(Settings.from_env(os.environ)))


if __name__ == "__main__":
    main()
