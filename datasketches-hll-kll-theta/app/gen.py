import os
import numpy as np

DATA = os.environ.get("DATA_DIR", "/data")
PARTITIONS = 8
ROWS_PER_PARTITION = 1_250_000
USER_RANGE = 1_500_000
PARTITION_SHIFT = 100_000
ITEMS = 100_000


def platform_for(users, rng):
    bucket = users % 5
    random_side = rng.integers(0, 2, users.size)
    return np.where(bucket < 3, 0, np.where(bucket == 3, 1, random_side)).astype(np.int8)


def partition(p, rng):
    users = (p * PARTITION_SHIFT + rng.integers(0, USER_RANGE, ROWS_PER_PARTITION)).astype(np.int64)
    platform = platform_for(users, rng)
    latency = rng.lognormal(3.5, 0.8, ROWS_PER_PARTITION) + platform * 15.0
    items = ((rng.zipf(1.3, ROWS_PER_PARTITION) - 1) % ITEMS + 1).astype(np.int32)
    return {"user": users, "platform": platform, "latency": latency.astype(np.float32), "item": items}


def main():
    os.makedirs(DATA, exist_ok=True)
    rng = np.random.default_rng(17)
    for p in range(PARTITIONS):
        np.savez(os.path.join(DATA, f"part-{p}.npz"), **partition(p, rng))
        print(f"wrote part-{p}.npz with {ROWS_PER_PARTITION} rows")


if __name__ == "__main__":
    main()
