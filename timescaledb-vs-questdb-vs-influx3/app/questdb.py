import json
import os
import time
from datetime import datetime
from urllib.parse import quote
from dataset import MINUTE_WINDOW, SCAN_DEVICE, SCAN_WINDOW
from rest import call

LABEL = "QuestDB"
PORT = int(os.environ.get("S7_QUESTDB_PORT", "30601"))
ROLLUP = "materialized view readings_1h, incremental refresh"


def micros(epoch):
    return epoch * 1000000


def downsample(width, where=""):
    return f"""SELECT device, ts AS bucket, avg(temperature) AS avg_t, min(temperature) AS min_t,
        max(temperature) AS max_t FROM readings {where} SAMPLE BY {width}"""


QUERIES = {
    "downsample_1h": [downsample("1h")],
    "downsample_1m": [downsample("1m", f"WHERE ts >= {micros(MINUTE_WINDOW[0])} AND ts < {micros(MINUTE_WINDOW[1])}")],
    "last_value": ["SELECT device, ts, temperature FROM readings LATEST ON ts PARTITION BY device"],
    "range_scan": [f"""SELECT ts, temperature, humidity FROM readings WHERE device = '{SCAN_DEVICE}'
        AND ts >= {micros(SCAN_WINDOW[0])} AND ts < {micros(SCAN_WINDOW[1])}"""],
    "rollup_1h": ["SELECT device, bucket, avg_t, min_t, max_t FROM readings_1h"],
}


def execute(sql):
    return json.loads(call(PORT, "GET", "/exec?query=" + quote(" ".join(sql.split())))).get("dataset", [])


def version():
    return execute("SELECT build")[0][0].split(",")[0].replace("Build Information: ", "")


def setup():
    execute("""CREATE TABLE readings (ts TIMESTAMP, device SYMBOL, temperature DOUBLE, humidity DOUBLE)
        TIMESTAMP(ts) PARTITION BY DAY WAL""")


def encode(chunk):
    return "".join(f"readings,device={device} temperature={t},humidity={h} {ts}\n" for device, ts, t, h in chunk).encode()


def send(payload):
    call(PORT, "POST", "/write?precision=s", payload)


def count():
    return execute("SELECT count() FROM readings")[0][0]


def disk():
    data = execute("SELECT sum(diskSize) FROM table_partitions('readings')")[0][0]
    total = execute("SELECT diskSize FROM table_storage() WHERE tableName = 'readings'")[0][0]
    return {"data": data, "wal": total - data}


def build_rollup():
    execute(f"CREATE MATERIALIZED VIEW readings_1h AS ({downsample('1h')}) PARTITION BY DAY")
    while True:
        status, done, base = execute("""SELECT view_status, refresh_base_table_txn, base_table_txn
            FROM materialized_views() WHERE view_name = 'readings_1h'""")[0]
        if status == "valid" and done == base:
            return
        if status == "invalid":
            raise RuntimeError("materialized view readings_1h is invalid")
        time.sleep(0.05)


def query(name):
    return [row for sql in QUERIES[name] for row in execute(sql)]


def hourly(rows):
    return [(device, int(datetime.fromisoformat(bucket).timestamp()), a, lo, hi) for device, bucket, a, lo, hi in rows]
