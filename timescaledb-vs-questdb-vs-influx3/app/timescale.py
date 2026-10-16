import os
import threading
from datetime import datetime, timezone
import psycopg
from dataset import MINUTE_WINDOW, SCAN_DEVICE, SCAN_WINDOW

LABEL = "TimescaleDB"
DSN = f"postgresql://s7:s7password@127.0.0.1:{os.environ.get('S7_TIMESCALEDB_PORT', '30600')}/s7"
LOCAL = threading.local()
ROLLUP = "continuous aggregate readings_1h, refreshed with refresh_continuous_aggregate"


def stamp(epoch):
    return datetime.fromtimestamp(epoch, timezone.utc).strftime("%Y-%m-%d %H:%M:%S+00")


def downsample(width, where=""):
    return f"""SELECT device, time_bucket('{width}', ts) AS bucket, avg(temperature) AS avg_t,
        min(temperature) AS min_t, max(temperature) AS max_t FROM readings {where} GROUP BY 1, 2"""


QUERIES = {
    "downsample_1h": [downsample("1 hour")],
    "downsample_1m": [downsample("1 minute", f"WHERE ts >= '{stamp(MINUTE_WINDOW[0])}' AND ts < '{stamp(MINUTE_WINDOW[1])}'")],
    "last_value": ["SELECT DISTINCT ON (device) device, ts, temperature FROM readings ORDER BY device, ts DESC"],
    "range_scan": [f"""SELECT ts, temperature, humidity FROM readings WHERE device = '{SCAN_DEVICE}'
        AND ts >= '{stamp(SCAN_WINDOW[0])}' AND ts < '{stamp(SCAN_WINDOW[1])}' ORDER BY ts"""],
    "rollup_1h": ["SELECT device, bucket, avg_t, min_t, max_t FROM readings_1h"],
}


def connection():
    if not hasattr(LOCAL, "con"):
        LOCAL.con = psycopg.connect(DSN, autocommit=True)
    return LOCAL.con


def execute(sql):
    cur = connection().execute(sql)
    return cur.fetchall() if cur.description else []


def version():
    extension = execute("SELECT extversion FROM pg_extension WHERE extname = 'timescaledb'")[0][0]
    return f"TimescaleDB {extension} on PostgreSQL {execute('SHOW server_version')[0][0]}"


def setup():
    execute("""CREATE TABLE readings (ts TIMESTAMPTZ NOT NULL, device TEXT NOT NULL,
        temperature DOUBLE PRECISION, humidity DOUBLE PRECISION)""")
    execute("SELECT create_hypertable('readings', by_range('ts', INTERVAL '1 day'))")
    execute("CREATE INDEX readings_device_ts ON readings (device, ts DESC)")


def encode(chunk):
    return "".join(f"{stamp(int(ts))}\t{device}\t{t}\t{h}\n" for device, ts, t, h in chunk).encode()


def send(payload):
    with connection().cursor().copy("COPY readings (ts, device, temperature, humidity) FROM STDIN") as copy:
        copy.write(payload)


def count():
    return execute("SELECT count(*) FROM readings")[0][0]


def disk():
    data, wal = execute("SELECT hypertable_size('readings'), (SELECT sum(size) FROM pg_ls_waldir())")[0]
    return {"data": data, "wal": int(wal)}


def compress():
    execute("""ALTER TABLE readings SET (timescaledb.compress, timescaledb.compress_segmentby = 'device',
        timescaledb.compress_orderby = 'ts DESC')""")
    execute("SELECT compress_chunk(c) FROM show_chunks('readings') c")
    execute("VACUUM ANALYZE readings")


def build_rollup():
    execute(f"""CREATE MATERIALIZED VIEW readings_1h WITH (timescaledb.continuous) AS
        {downsample('1 hour')} WITH NO DATA""")
    execute("CALL refresh_continuous_aggregate('readings_1h', NULL, NULL)")


def query(name):
    return [row for sql in QUERIES[name] for row in execute(sql)]


def hourly(rows):
    return [(device, int(bucket.timestamp()), a, lo, hi) for device, bucket, a, lo, hi in rows]
