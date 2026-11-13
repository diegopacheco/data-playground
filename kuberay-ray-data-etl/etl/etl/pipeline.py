import time

import ray.data

from etl.store import SUCCESS, Commit, Ready, Store
from etl.transform import GROUP_KEYS, aggregations, clean_events


def now_ms() -> int:
    return time.time_ns() // 1_000_000


def process(store: Store, ready: Ready) -> Commit:
    started = now_ms()
    out = f"output/{ready.batch_id}"
    store.clear(out)
    events = (
        ray.data.read_json([store.path(f) for f in ready.files], filesystem=store.fs)
        .map_batches(clean_events, batch_format="pyarrow")
        .materialize()
    )
    events.write_parquet(store.path(f"{out}/events"), filesystem=store.fs)
    events.groupby(GROUP_KEYS).aggregate(*aggregations()).write_parquet(store.path(f"{out}/aggregates"), filesystem=store.fs)
    commit = Commit(ready.batch_id, ready.ready_at_ms, started, now_ms(), events.count())
    store.write_text(f"{out}/{SUCCESS}", commit.to_json())
    return commit
