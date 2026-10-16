import csv
import os
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV = os.path.join(ROOT, "data", "readings.csv")
RESULTS = os.path.join(ROOT, ".run", "results.json")
SEED = 7
DEVICES = 200
DAYS = 4
STEP = 10
START = int(datetime(2026, 10, 1, tzinfo=timezone.utc).timestamp())
STOP = START + DAYS * 86400
POINTS = DEVICES * DAYS * 86400 // STEP
BATCH = 10000
WORKERS = 4
RUNS = 21
MINUTE_WINDOW = (START + 2 * 86400 + 6 * 3600, START + 2 * 86400 + 12 * 3600)
SCAN_DEVICE = "d042"
SCAN_WINDOW = (START + 3 * 86400 + 9 * 3600, START + 3 * 86400 + 9 * 3600 + 900)


def batches():
    with open(CSV, newline="") as f:
        reader = csv.reader(f)
        next(reader)
        chunk = []
        for row in reader:
            chunk.append(row)
            if len(chunk) == BATCH:
                yield chunk
                chunk = []
        if chunk:
            yield chunk
