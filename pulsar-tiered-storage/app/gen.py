import csv
import os
import random
from pathlib import Path

ROWS = int(os.environ.get("ROWS", "500"))
SENSORS = ["boiler", "chiller", "pump-a", "pump-b", "turbine"]


def main():
    rng = random.Random(7)
    path = Path(os.environ.get("DATA_DIR", "/app/data"), "readings.csv")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        out = csv.writer(f)
        out.writerow(["seq", "sensor", "value_milli", "ts"])
        for seq in range(1, ROWS + 1):
            out.writerow([seq, rng.choice(SENSORS), rng.randint(-20000, 120000), f"2026-09-26T{seq // 3600 % 24:02d}:{seq // 60 % 60:02d}:{seq % 60:02d}Z"])
    print(f"wrote {ROWS} rows to {path}")


if __name__ == "__main__":
    main()
