import os
import threading
import time
import psycopg
from queries import COLUMNS, PROBE, QUERIES, normalize

URL = os.environ.get("MZ_URL", "postgresql://materialize@localhost:31101/materialize")
BROKER = os.environ.get("ENGINE_BROKER", "t2-redpanda:9092")


def connect():
    return psycopg.connect(URL, autocommit=True, connect_timeout=10)


def plain(v):
    if v is None or isinstance(v, (str, int)):
        return v
    return int(v)


def ddl(topics):
    stmts = [
        f"CREATE CONNECTION IF NOT EXISTS kafka_conn TO KAFKA (BROKER '{BROKER}', SECURITY PROTOCOL PLAINTEXT)",
        f"CREATE SOURCE orders_src FROM KAFKA CONNECTION kafka_conn (TOPIC '{topics['orders']}') KEY FORMAT TEXT VALUE FORMAT JSON ENVELOPE UPSERT WITH (TIMESTAMP INTERVAL '100ms')",
        f"CREATE SOURCE customers_src FROM KAFKA CONNECTION kafka_conn (TOPIC '{topics['customers']}') KEY FORMAT TEXT VALUE FORMAT JSON ENVELOPE UPSERT WITH (TIMESTAMP INTERVAL '100ms')",
        "CREATE VIEW orders AS SELECT (data->>'order_id')::int AS order_id, data->>'customer_id' AS customer_id, (data->>'amount')::int AS amount, data->>'status' AS status FROM orders_src",
        "CREATE VIEW customers AS SELECT data->>'customer_id' AS customer_id, data->>'name' AS name, data->>'region' AS region FROM customers_src",
        "CREATE INDEX orders_idx ON orders (order_id)",
        "CREATE INDEX customers_idx ON customers (customer_id)",
    ]
    for name, sql in QUERIES.items():
        stmts.append(f"CREATE MATERIALIZED VIEW {name} WITH (RETAIN HISTORY FOR '10m') AS {sql}")
    return stmts


def drop():
    with connect() as c:
        c.execute("DROP SOURCE IF EXISTS orders_src CASCADE")
        c.execute("DROP SOURCE IF EXISTS customers_src CASCADE")


def setup(topics):
    statements = ddl(topics)
    with connect() as c:
        for s in statements:
            c.execute(s)
        for name in QUERIES:
            c.execute(f"SELECT * FROM {name}").fetchall()
        start = int(c.execute("SELECT mz_now()").fetchone()[0])
    return statements, start


def ingested(topic_source):
    with connect() as c:
        return int(c.execute(f"SELECT \"offset\" FROM {topic_source}_progress WHERE partition = '[0,0]'").fetchone()[0])


def wait_ingested(source, count, timeout=60):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if ingested(source) >= count:
            return True
        time.sleep(0.05)
    return False


def read_all(real_time_recency):
    started = time.time()
    with connect() as c:
        c.execute(f"SET real_time_recency = {'true' if real_time_recency else 'false'}")
        c.execute("BEGIN READ ONLY")
        out = {name: normalize([[plain(v) for v in r] for r in c.execute(f"SELECT {', '.join(COLUMNS[name])} FROM {name}").fetchall()]) for name in QUERIES}
        ts = int(c.execute("SELECT mz_now()").fetchone()[0])
        c.execute("COMMIT")
    return {"timestamp": ts, "ms": round((time.time() - started) * 1000), "results": out}


def subscribe(name, start, end):
    with connect() as c:
        rows = c.execute(f"SUBSCRIBE (SELECT {', '.join(COLUMNS[name])} FROM {name}) AS OF {start} UP TO {end}").fetchall()
    return [[int(r[0]), int(r[1])] + [plain(v) for v in r[2:]] for r in rows]


def now():
    with connect() as c:
        return int(c.execute("SELECT mz_now()").fetchone()[0])


class Probe(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.samples = []
        self.errors = []
        self.halt = threading.Event()

    def run(self):
        with connect() as c:
            while not self.halt.is_set():
                try:
                    row = c.execute(PROBE.replace("SELECT ", "SELECT mz_now(), ", 1)).fetchone()
                    self.samples.append([plain(v) for v in row])
                except Exception as e:
                    self.errors.append(f"{type(e).__name__}: {e}")
                time.sleep(0.02)

    def stop(self):
        self.halt.set()
        self.join(timeout=10)
