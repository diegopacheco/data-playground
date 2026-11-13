import gc
import os
import time
from collections.abc import Collection
from concurrent.futures import Future, ThreadPoolExecutor

import ray
from ray.data import DataContext
from ray.data.context import ShuffleStrategy

from etl.config import Settings
from etl.pipeline import process
from etl.store import Commit, Store, s3


def next_to_start(pending: list[str], in_flight: Collection[str], capacity: int) -> list[str]:
    free = capacity - len(in_flight)
    return [batch for batch in pending if batch not in in_flight][: max(free, 0)]


def configure_ray_data() -> None:
    context = DataContext.get_current()
    context.shuffle_strategy = ShuffleStrategy.SORT_SHUFFLE_PULL_BASED
    context.enable_progress_bars = False


def run(settings: Settings, store: Store) -> None:
    in_flight: dict[str, Future[Commit]] = {}
    with ThreadPoolExecutor(settings.parallel_batches) as pool:
        while True:
            finished = [batch_id for batch_id, future in in_flight.items() if future.done()]
            for batch_id in finished:
                commit = in_flight.pop(batch_id).result()
                latency = commit.committed_at_ms - commit.ready_at_ms
                print(f"COMMIT batch={batch_id} rows={commit.rows} latency_ms={latency}", flush=True)
            if finished:
                gc.collect()
            for batch_id in next_to_start(store.pending(), in_flight, settings.parallel_batches):
                in_flight[batch_id] = pool.submit(process, store, store.ready(batch_id))
            time.sleep(settings.poll_seconds)


def main() -> None:
    settings = Settings.from_env(os.environ)
    ray.init()
    configure_ray_data()
    store = Store(s3(settings), settings.bucket)
    store.ensure_bucket()
    print(f"etl driver started bucket={settings.bucket} parallel={settings.parallel_batches}", flush=True)
    run(settings, store)


if __name__ == "__main__":
    main()
