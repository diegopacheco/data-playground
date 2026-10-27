import csv
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORDERS_CSV = os.path.join(ROOT, "data", "orders.csv")
LAG_FILE = os.path.join(ROOT, ".run", "lag.json")

with open(os.path.join(ROOT, "scripts", "ports.env")) as f:
    PORTS = dict(line.strip().split("=") for line in f if "=" in line)

PROXY = f"http://localhost:{PORTS['proxy']}"
REGISTRY = f"http://localhost:{PORTS['registry']}"
ADMIN = f"http://localhost:{PORTS['admin']}"
REST = f"http://localhost:{PORTS['rest']}"
MINIO = f"localhost:{PORTS['minio']}"
UI_PORT = int(PORTS["ui"])

SUBJECT = "orders_typed-value"
ORDER_SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "properties": {
        "order_id": {"type": "integer"},
        "customer": {"type": "string"},
        "product": {"type": "string"},
        "category": {"type": "string"},
        "quantity": {"type": "integer"},
        "price": {"type": "number"},
        "ts": {"type": "string", "format": "date-time"},
    },
    "required": ["order_id", "customer", "product", "category", "quantity", "price", "ts"],
    "additionalProperties": False,
}

TOPICS = {
    "orders_kv": {
        "mode": "key_value",
        "sample": "SELECT redpanda::VARCHAR AS redpanda, decode(value) AS \"decode(value)\" FROM lake.redpanda.orders_kv",
        "orders": "SELECT v->>'category' AS category, (v->>'quantity')::BIGINT AS quantity, (v->>'price')::DECIMAL(10,2) AS price "
                  "FROM (SELECT decode(value)::JSON AS v FROM lake.redpanda.orders_kv)",
    },
    "orders_typed": {
        "mode": "value_schema_id_prefix",
        "sample": "SELECT COLUMNS(*)::VARCHAR FROM lake.redpanda.orders_typed",
        "orders": "SELECT category, quantity, price::DECIMAL(10,2) AS price FROM lake.redpanda.orders_typed",
    },
}


def orders():
    with open(ORDERS_CSV) as f:
        return [{**r, "order_id": int(r["order_id"]), "quantity": int(r["quantity"]), "price": float(r["price"])}
                for r in csv.DictReader(f)]
