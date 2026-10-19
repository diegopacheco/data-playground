import json
import os
import statistics
import sys
import threading
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd
import redis
from feast import FeatureStore
from feast.data_source import PushMode
from feast.protos.feast.serving.ServingService_pb2 import FieldStatus

REPO = os.environ.get("FEAST_REPO", "/app/repo")
DATA = Path(os.environ.get("DATA_DIR", "/data"))
REDIS_HOST = os.environ.get("REDIS_HOST", "r16-redis")
FEATURE_SERVER = os.environ.get("FEATURE_SERVER_URL", "http://r16-feature-server:6566")
SERVICE = "driver_model_v1"
STATE = DATA / "state.json"
sys.path.insert(0, REPO)
sys.path.insert(0, str(Path(__file__).parent))
import features
import gen

LOCK = threading.Lock()


def store():
    return FeatureStore(repo_path=REPO)


def iso(ts):
    return pd.Timestamp(ts).isoformat() if ts is not None and not pd.isna(ts) else None


def views(fs):
    return {fv.name: fv for fv in fs.list_feature_views()}


def bootstrap():
    with LOCK:
        anchor = gen.generate(DATA)
        (DATA / "registry.db").unlink(missing_ok=True)
        redis.Redis(host=REDIS_HOST).flushdb()
        fs = store()
        fs.apply([features.driver, features.hourly_source, features.hourly_push, features.daily_source, features.driver_hourly, features.driver_daily, features.driver_model_v1])
        end = datetime.now(timezone.utc)
        started = time.perf_counter()
        fs.materialize_incremental(end_date=end)
        took = time.perf_counter() - started
        windows = {name: {"start": iso(end - fv.ttl), "end": iso(end), "ttl_seconds": int(fv.ttl.total_seconds())} for name, fv in views(fs).items()}
        state = {"anchor": iso(anchor), "materialized_at": iso(end), "materialize_seconds": round(took, 3), "windows": windows, "pushes": []}
        STATE.write_text(json.dumps(state, indent=1))
        training = historical(fs)
        training.to_parquet(DATA / "training.parquet", index=False)
        return state


def state():
    return json.loads(STATE.read_text())


def historical(fs=None):
    fs = fs or store()
    labels = pd.read_parquet(DATA / "labels.parquet")
    job = fs.get_historical_features(entity_df=labels, features=fs.get_feature_service(SERVICE), full_feature_names=True)
    return job.to_df().sort_values("request_id").reset_index(drop=True)


def naive_latest():
    labels = pd.read_parquet(DATA / "labels.parquet")
    hourly = pd.read_parquet(DATA / "driver_hourly.parquet").sort_values("event_timestamp").groupby("driver_id").tail(1)
    hourly = hourly[["driver_id", "conv_rate", "observed_at"]].rename(columns={"conv_rate": "naive_conv_rate", "observed_at": "naive_observed_at"})
    return labels.merge(hourly, on="driver_id", how="left").sort_values("request_id").reset_index(drop=True)


def clean(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    if hasattr(v, "item"):
        return v.item()
    return v


def training_report():
    pit = pd.read_parquet(DATA / "training.parquet")
    naive = naive_latest()
    merged = pit.merge(naive[["request_id", "naive_conv_rate", "naive_observed_at"]], on="request_id")
    rows = []
    for r in merged.itertuples(index=False):
        label_ts = int(pd.Timestamp(r.event_timestamp).timestamp())
        rows.append({
            "request_id": int(r.request_id), "driver_id": int(r.driver_id), "event_timestamp": iso(r.event_timestamp), "label_epoch": label_ts, "trip_accepted": int(r.trip_accepted),
            "conv_rate": clean(r.driver_hourly__conv_rate), "trips_today": clean(r.driver_hourly__trips_today), "hourly_observed_at": clean(r.driver_hourly__observed_at),
            "rating": clean(r.driver_daily__rating), "daily_observed_at": clean(r.driver_daily__observed_at),
            "naive_conv_rate": clean(r.naive_conv_rate), "naive_observed_at": clean(r.naive_observed_at),
            "naive_leaks": bool(r.naive_observed_at > label_ts),
        })
    pit_future = sum(1 for r in rows for k in ("hourly_observed_at", "daily_observed_at") if r[k] is not None and r[k] > r["label_epoch"])
    return {
        "rows": rows,
        "summary": {
            "labels": len(rows),
            "pit_future_values": pit_future,
            "naive_future_values": sum(r["naive_leaks"] for r in rows),
            "naive_differs": sum(1 for r in rows if r["conv_rate"] != r["naive_conv_rate"]),
            "hourly_null_by_ttl": sum(1 for r in rows if r["conv_rate"] is None),
            "daily_null_by_ttl": sum(1 for r in rows if r["rating"] is None),
        },
    }


def online(driver_ids, fs=None):
    fs = fs or store()
    fvs = views(fs)
    started = time.perf_counter()
    resp = fs.get_online_features(features=fs.get_feature_service(SERVICE), entity_rows=[{"driver_id": d} for d in driver_ids], full_feature_names=True)
    took = (time.perf_counter() - started) * 1000
    now = time.time()
    names = list(resp.proto.metadata.feature_names.val)
    data = resp.to_dict()
    out = [{"driver_id": d, "features": {}} for d in driver_ids]
    for name, vec in zip(names, resp.proto.results):
        if name == "driver_id":
            continue
        view = name.split("__")[0]
        ttl = int(fvs[view].ttl.total_seconds())
        values = data[name]
        for i, d in enumerate(driver_ids):
            ts = vec.event_timestamps[i].seconds
            found = vec.statuses[i] == FieldStatus.PRESENT and ts > 0 and values[i] is not None
            age = int(now - ts) if found else None
            out[i]["features"][name] = {"value": values[i], "status": FieldStatus.Name(vec.statuses[i]), "found": found, "event_epoch": ts if found else None, "age_seconds": age, "ttl_seconds": ttl, "fresh": found and age <= ttl}
    return {"latency_ms": round(took, 3), "rows": out}


def push(driver_id, conv_rate, acc_rate, trips_today):
    with LOCK:
        now = datetime.now(timezone.utc).replace(microsecond=0)
        df = pd.DataFrame([{"driver_id": int(driver_id), "event_timestamp": now, "created": now, "conv_rate": float(conv_rate), "acc_rate": float(acc_rate), "trips_today": int(trips_today), "observed_at": int(now.timestamp())}])
        df["event_timestamp"] = pd.to_datetime(df["event_timestamp"], utc=True)
        df["created"] = pd.to_datetime(df["created"], utc=True)
        store().push("driver_hourly_push", df, to=PushMode.ONLINE)
        s = state()
        s["pushes"].append({"driver_id": int(driver_id), "event_timestamp": iso(now), "conv_rate": float(conv_rate)})
        STATE.write_text(json.dumps(s, indent=1))
        return s["pushes"][-1]


def http_online(driver_ids):
    body = json.dumps({"feature_service": SERVICE, "entities": {"driver_id": driver_ids}, "full_feature_names": True}).encode()
    req = urllib.request.Request(FEATURE_SERVER + "/get-online-features", data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def percentiles(samples):
    s = sorted(samples)
    pick = lambda p: round(s[min(len(s) - 1, int(p * len(s)))], 3)
    return {"n": len(s), "p50": pick(0.5), "p95": pick(0.95), "p99": pick(0.99), "max": round(s[-1], 3), "mean": round(statistics.fmean(s), 3)}


def latency(n=200):
    fs = store()
    ids = gen.DRIVERS
    sdk, http = [], []
    service = fs.get_feature_service(SERVICE)
    fs.get_online_features(features=service, entity_rows=[{"driver_id": ids[0]}], full_feature_names=True)
    http_online([ids[0]])
    for i in range(n):
        d = ids[i % len(ids)]
        t = time.perf_counter()
        fs.get_online_features(features=service, entity_rows=[{"driver_id": d}], full_feature_names=True)
        sdk.append((time.perf_counter() - t) * 1000)
        t = time.perf_counter()
        http_online([d])
        http.append((time.perf_counter() - t) * 1000)
    return {"requests": n, "entities_per_request": 1, "sdk_ms": percentiles(sdk), "feature_server_ms": percentiles(http)}


def definitions():
    fs = store()
    return {
        "project": fs.project,
        "entities": [{"name": e.name, "join_key": e.join_key, "description": e.description} for e in fs.list_entities()],
        "feature_views": [{"name": fv.name, "ttl_seconds": int(fv.ttl.total_seconds()), "source": fv.batch_source.path, "push_source": fv.stream_source.name if fv.stream_source else None, "features": [{"name": f.name, "dtype": str(f.dtype)} for f in fv.features], "description": fv.description} for fv in fs.list_feature_views()],
        "feature_services": [{"name": s.name, "views": [p.name for p in s.feature_view_projections]} for s in fs.list_feature_services()],
        "online_store": "redis", "offline_store": "duckdb (Parquet files)",
    }


def timeline(driver_id):
    hourly = pd.read_parquet(DATA / "driver_hourly.parquet")
    labels = pd.read_parquet(DATA / "labels.parquet")
    h = hourly[hourly.driver_id == driver_id].sort_values("event_timestamp")
    l = labels[labels.driver_id == driver_id].sort_values("event_timestamp")
    return {
        "driver_id": driver_id,
        "updates": [{"epoch": int(r.observed_at), "conv_rate": float(r.conv_rate)} for r in h.itertuples()],
        "labels": [{"request_id": int(r.request_id), "epoch": int(pd.Timestamp(r.event_timestamp).timestamp())} for r in l.itertuples()],
    }
