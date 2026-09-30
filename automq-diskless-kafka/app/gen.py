import json
import os
import random
from pathlib import Path

OUT = Path(os.environ.get("DATA_FILE", "/data/orders.jsonl"))
ROWS = int(os.environ.get("ROWS", "20000"))


def main():
    rng = random.Random(2026)
    regions = ["north", "south", "east", "west"]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w") as out:
        for i in range(ROWS):
            order = {"order_id": f"o-{i:06d}", "customer_id": rng.randint(1, 2000), "region": rng.choice(regions), "quantity": rng.randint(1, 9), "price_cents": rng.randint(99, 49999), "note": "".join(rng.choice("abcdefghijklmnopqrstuvwxyz") for _ in range(rng.randint(40, 200)))}
            out.write(json.dumps(order, separators=(",", ":")) + "\n")
    print(f"wrote {ROWS} orders to {OUT}")


if __name__ == "__main__":
    main()
