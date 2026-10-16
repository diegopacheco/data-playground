import json
import os
import subprocess
import time
from datetime import datetime, timezone
from dataset import MINUTE_WINDOW, POINTS, SCAN_DEVICE, SCAN_WINDOW, START, STOP
from rest import HttpError, call

LABEL = "InfluxDB 3 Core"
PORT = int(os.environ.get("S7_INFLUX3_PORT", "30602"))
DB = "s7"
JSON = {"Content-Type": "application/json"}
ROLLUP = "no built-in equivalent: processing engine request trigger running app/plugins/rollup.py once per day of data"
DAYS = [(day, day + 86400) for day in range(START, STOP, 86400)]


def between(window):
    return f"time >= to_timestamp_seconds({window[0]}) AND time < to_timestamp_seconds({window[1]})"


def downsample(width, where=""):
    return f"""SELECT device, date_bin(INTERVAL '{width}', time) AS bucket, avg(temperature) AS avg_t,
        min(temperature) AS min_t, max(temperature) AS max_t FROM readings {where} GROUP BY 1, 2"""


FULL_RANGE = downsample("1 hour")
QUERIES = {
    "downsample_1h": [downsample("1 hour", "WHERE " + between(day)) for day in DAYS],
    "downsample_1m": [downsample("1 minute", "WHERE " + between(MINUTE_WINDOW))],
    "last_value": [f"""SELECT device, selector_last(temperature, time)['time'] AS ts,
        selector_last(temperature, time)['value'] AS temperature FROM readings
        WHERE {between(DAYS[-1])} GROUP BY device"""],
    "range_scan": [f"""SELECT time, temperature, humidity FROM readings WHERE device = '{SCAN_DEVICE}'
        AND {between(SCAN_WINDOW)} ORDER BY time"""],
    "rollup_1h": ["SELECT device, time AS bucket, avg_t, min_t, max_t FROM readings_1h"],
}


def execute(sql):
    body = json.dumps({"db": DB, "q": " ".join(sql.split()), "format": "json"})
    return [list(row.values()) for row in json.loads(call(PORT, "POST", "/api/v3/query_sql", body, JSON))]


def version():
    return "InfluxDB 3 Core " + json.loads(call(PORT, "GET", "/ping"))["version"]


def setup():
    call(PORT, "POST", "/api/v3/configure/database", json.dumps({"db": DB}), JSON)


def encode(chunk):
    return "".join(f"readings,device={device} temperature={t},humidity={h} {ts}\n" for device, ts, t, h in chunk).encode()


def send(payload):
    call(PORT, "POST", f"/api/v3/write_lp?db={DB}&precision=second", payload)


def count():
    return sum(execute(f"SELECT count(*) FROM readings WHERE {between(day)}")[0][0] for day in DAYS)


def disk():
    out = subprocess.run(["podman", "exec", "s7-influx3", "du", "-sb", "/var/lib/influxdb3"],
                         capture_output=True, text=True, check=True).stdout
    files, data, rows = execute("""SELECT count(*), sum(size_bytes), sum(row_count) FROM system.parquet_files
        WHERE table_name = 'readings'""")[0]
    return {"data": data or 0, "wal": int(out.split()[0]) - (data or 0), "parquet_files": files, "parquet_rows": rows or 0}


def persist():
    started = time.perf_counter()
    while disk()["parquet_rows"] != POINTS:
        if time.perf_counter() - started > 60:
            raise RuntimeError("readings were not persisted to Parquet within 60 seconds")
        time.sleep(0.2)
    return round(time.perf_counter() - started, 2)


def full_range_error():
    try:
        execute(FULL_RANGE)
    except HttpError as e:
        return str(e)
    return ""


def build_rollup():
    body = {"db": DB, "plugin_filename": "rollup.py", "trigger_name": "rollup", "trigger_specification": "request:rollup",
            "trigger_settings": {"run_async": False, "error_behavior": "log"}, "disabled": False}
    call(PORT, "POST", "/api/v3/configure/processing_engine_trigger", json.dumps(body), JSON)
    for start, stop in DAYS:
        call(PORT, "POST", f"/api/v3/engine/rollup?start={start}&stop={stop}")


def query(name):
    return [row for sql in QUERIES[name] for row in execute(sql)]


def hourly(rows):
    return [(device, int(datetime.fromisoformat(bucket).replace(tzinfo=timezone.utc).timestamp()), a, lo, hi)
            for device, bucket, a, lo, hi in rows]
