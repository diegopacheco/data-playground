import base64
import json
import struct
import time
import duckdb
from config import LAG_FILE, ORDER_SCHEMA, PROXY, REGISTRY, SUBJECT, TOPICS, orders
from lake import connect, http

BATCH = 50
POLL_SECONDS = 0.5
MAX_POLLS = 120


def b64(raw):
    return base64.b64encode(raw).decode()


def register_schema():
    body = {"schemaType": "JSON", "schema": json.dumps(ORDER_SCHEMA)}
    return http(f"{REGISTRY}/subjects/{SUBJECT}/versions", body, "application/vnd.schemaregistry.v1+json")["id"]


def encode(order, mode, schema_id):
    payload = json.dumps(order).encode()
    if mode == "value_schema_id_prefix":
        return b"\0" + struct.pack(">I", schema_id) + payload
    return payload


def produce(topic, mode, batch, schema_id):
    records = [{"key": b64(str(o["order_id"]).encode()), "value": b64(encode(o, mode, schema_id))} for o in batch]
    reply = http(f"{PROXY}/topics/{topic}", {"records": records}, "application/vnd.kafka.binary.v2+json")
    failed = [o for o in reply["offsets"] if o.get("error_code")]
    if failed:
        raise RuntimeError(f"produce to {topic} failed: {failed}")
    return time.time()


def table_count(topic):
    try:
        return connect().execute(f"SELECT count(*) FROM lake.redpanda.{topic}").fetchone()[0]
    except duckdb.Error:
        return 0


def wait_visible(pending, expected):
    seen = {}
    for _ in range(MAX_POLLS):
        for topic in pending:
            if topic not in seen and table_count(topic) >= expected:
                seen[topic] = time.time()
        if len(seen) == len(pending):
            return seen
        time.sleep(POLL_SECONDS)
    raise RuntimeError(f"rows not visible in iceberg after {MAX_POLLS * POLL_SECONDS:.0f}s: expected {expected}, saw {seen}")


def main():
    schema_id = register_schema()
    all_orders = orders()
    batches = []
    for start in range(0, len(all_orders), BATCH):
        batch = all_orders[start:start + BATCH]
        produced = {topic: produce(topic, cfg["mode"], batch, schema_id) for topic, cfg in TOPICS.items()}
        visible = wait_visible(produced, start + len(batch))
        for topic in TOPICS:
            lag = round(visible[topic] - produced[topic], 2)
            batches.append({"batch": start // BATCH + 1, "topic": topic, "records": len(batch),
                            "produced_at_ms": int(produced[topic] * 1000), "visible_after_s": lag})
            print(f"batch {start // BATCH + 1} {topic}: {len(batch)} records readable from iceberg after {lag}s")
    with open(LAG_FILE, "w") as f:
        json.dump({"schema_id": schema_id, "batches": batches}, f)


if __name__ == "__main__":
    main()
