import random

REGIONS = ["us", "eu", "br", "jp", "in"]
DAYS = ["2026-10-01", "2026-10-02", "2026-10-03", "2026-10-04", "2026-10-05", "2026-10-06", "2026-10-07"]


def orders(seed, rows):
    rng = random.Random(seed)
    return [
        {"id": i, "region": rng.choice(REGIONS), "day": rng.choice(DAYS), "cents": rng.randint(100, 90000)}
        for i in range(1, rows + 1)
    ]
