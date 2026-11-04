import json
import random

REGIONS = ["us", "eu", "br", "jp"]


def orders(count, seed=8, start=1):
    rng = random.Random(seed)
    rows = [{"id": i, "region": rng.choice(REGIONS), "cents": rng.randint(100, 50000)} for i in range(1, start + count)]
    return rows[start - 1:]


def encode(row):
    return json.dumps(row, separators=(",", ":")).encode()


def decode(data):
    return json.loads(data)
