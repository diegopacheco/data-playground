import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
import pandas as pd

DRIVERS = list(range(1001, 1021))
HOURLY_STOP = {1017: 30, 1018: 40, 1019: 60, 1020: 100}
DAILY_STOP = {1020: 9}
HOURS = 168
DAYS = 14
LABELS = 300


def hourly_rows(rng, anchor):
    rows = []
    for d in DRIVERS:
        trips = 0
        for h in range(HOURS - 1, HOURLY_STOP.get(d, 0) - 1, -1):
            ts = anchor - timedelta(hours=h, minutes=rng.randint(1, 50))
            trips = 0 if ts.hour == 0 else trips + rng.randint(0, 3)
            rows.append({"driver_id": d, "event_timestamp": ts, "created": ts, "conv_rate": round(rng.uniform(0.2, 0.95), 4), "acc_rate": round(rng.uniform(0.5, 1.0), 4), "trips_today": trips})
    return rows


def daily_rows(rng, anchor):
    rows = []
    for d in DRIVERS:
        total = rng.randint(200, 3000)
        for day in range(DAYS - 1, DAILY_STOP.get(d, 0) - 1, -1):
            ts = anchor - timedelta(days=day, hours=2, minutes=rng.randint(0, 59))
            total += rng.randint(5, 25)
            rows.append({"driver_id": d, "event_timestamp": ts, "created": ts, "rating": round(rng.uniform(3.5, 5.0), 3), "lifetime_trips": total})
    return rows


def label_rows(rng, anchor):
    rows = []
    for _ in range(LABELS):
        ts = anchor - timedelta(seconds=rng.randint(60, 6 * 24 * 3600))
        rows.append({"driver_id": rng.choice(DRIVERS), "event_timestamp": ts, "trip_accepted": rng.randint(0, 1)})
    rows.sort(key=lambda r: r["event_timestamp"])
    return [{"request_id": i + 1, **r} for i, r in enumerate(rows)]


def frame(rows):
    df = pd.DataFrame(rows)
    if "created" in df:
        df["observed_at"] = [int(t.timestamp()) for t in df["event_timestamp"]]
    for c in ("event_timestamp", "created"):
        if c in df:
            df[c] = pd.to_datetime(df[c], utc=True)
    return df


def generate(data_dir):
    rng = random.Random(16)
    anchor = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    out = Path(data_dir)
    out.mkdir(parents=True, exist_ok=True)
    frame(hourly_rows(rng, anchor)).to_parquet(out / "driver_hourly.parquet", index=False)
    frame(daily_rows(rng, anchor)).to_parquet(out / "driver_daily.parquet", index=False)
    frame(label_rows(rng, anchor)).to_parquet(out / "labels.parquet", index=False)
    return anchor
