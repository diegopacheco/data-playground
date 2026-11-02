import json
import os
import time
import urllib.request
from queries import QUERIES, normalize

GATEWAY = os.environ.get("GATEWAY_URL", "http://localhost:31106")
BROKER = os.environ.get("ENGINE_BROKER", "t2-redpanda:9092")
ADD = {"INSERT", "UPDATE_AFTER"}


def call(method, path, body=None):
    req = urllib.request.Request(GATEWAY + path, method=method, data=None if body is None else json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"flink gateway {e.code}: {e.read().decode()[:2000]}") from None


def table(name, topic, columns):
    return (f"CREATE TABLE {name} (k STRING, {columns}, PRIMARY KEY (k) NOT ENFORCED) WITH ("
            f"'connector' = 'upsert-kafka', 'topic' = '{topic}', 'properties.bootstrap.servers' = '{BROKER}', "
            f"'key.format' = 'raw', 'value.format' = 'json', 'value.fields-include' = 'EXCEPT_KEY', "
            f"'scan.bounded.mode' = 'latest-offset')")


def ddl(topics):
    return [
        table("orders_topic", topics["orders"], "order_id INT, customer_id STRING, amount INT, status STRING"),
        table("customers_topic", topics["customers"], "customer_id STRING, name STRING, region STRING"),
        "CREATE VIEW orders AS SELECT order_id, customer_id, amount, status FROM orders_topic",
        "CREATE VIEW customers AS SELECT customer_id, name, region FROM customers_topic",
    ]


class Session:
    def __init__(self):
        self.handle = call("POST", "/v1/sessions", {"properties": {"execution.runtime-mode": "streaming", "parallelism.default": "1"}})["sessionHandle"]

    def run(self, sql, timeout=120):
        op = call("POST", f"/v1/sessions/{self.handle}/statements", {"statement": sql})["operationHandle"]
        uri = f"/v1/sessions/{self.handle}/operations/{op}/result/0?rowFormat=JSON"
        rows = []
        deadline = time.time() + timeout
        while uri:
            if time.time() > deadline:
                raise TimeoutError(f"flink statement did not finish in {timeout}s: {sql[:80]}")
            r = call("GET", uri)
            if r["resultType"] == "NOT_READY":
                time.sleep(0.2)
            rows += r.get("results", {}).get("data", [])
            if r["resultType"] == "EOS":
                break
            uri = r.get("nextResultUri")
        return rows

    def close(self):
        call("DELETE", f"/v1/sessions/{self.handle}")


def final_state(changelog):
    state = []
    for row in changelog:
        fields = row["fields"]
        if row["kind"] in ADD:
            state.append(fields)
        else:
            state.remove(fields)
    return normalize(state)


def run_all(topics):
    s = Session()
    out = {"ddl": ddl(topics), "results": {}, "changelog": {}, "ms": {}}
    try:
        for stmt in out["ddl"]:
            s.run(stmt)
        for name, sql in QUERIES.items():
            started = time.time()
            rows = s.run(sql)
            out["ms"][name] = round((time.time() - started) * 1000)
            out["changelog"][name] = [[r["kind"]] + r["fields"] for r in rows]
            out["results"][name] = final_state(rows)
    finally:
        s.close()
    return out
