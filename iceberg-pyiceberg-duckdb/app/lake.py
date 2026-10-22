import os
from urllib.parse import urlparse
import duckdb
import pyarrow as pa
import pyarrow.compute as pc
from pyiceberg.catalog import load_catalog

REST_URI = os.environ.get("REST_URI", "http://localhost:20602")
S3_ENDPOINT = os.environ.get("S3_ENDPOINT", "http://localhost:20600")
ACCESS_KEY = os.environ.get("S3_ACCESS_KEY", "i6admin")
SECRET_KEY = os.environ.get("S3_SECRET_KEY", "i6password")
REGION = "us-east-1"
NAMESPACE = "shop"
TABLE = f"{NAMESPACE}.orders"


def catalog():
    return load_catalog(
        "rest",
        type="rest",
        uri=REST_URI,
        **{
            "s3.endpoint": S3_ENDPOINT,
            "s3.access-key-id": ACCESS_KEY,
            "s3.secret-access-key": SECRET_KEY,
            "s3.region": REGION,
        },
    )


def to_rows(table):
    rows = []
    for r in table.to_pylist():
        rows.append({
            "category": r["category"],
            "total_orders": int(r["total_orders"]),
            "total_quantity": int(r["total_quantity"]),
            "total_revenue": round(float(r["total_revenue"]), 2),
        })
    return sorted(rows, key=lambda r: r["category"])


def pyiceberg_aggregates(snapshot_id=None):
    table = catalog().load_table(TABLE)
    data = table.scan(snapshot_id=snapshot_id).to_arrow()
    revenue = pc.multiply(pc.cast(data["quantity"], pa.float64()), data["price"])
    data = data.append_column("revenue", revenue)
    grouped = data.group_by("category").aggregate([("order_id", "count"), ("quantity", "sum"), ("revenue", "sum")])
    grouped = grouped.rename_columns({"order_id_count": "total_orders", "quantity_sum": "total_quantity", "revenue_sum": "total_revenue"})
    return to_rows(grouped)


def pyiceberg_snapshots():
    table = catalog().load_table(TABLE)
    current = table.current_snapshot().snapshot_id
    result = []
    for s in table.snapshots():
        summary = s.summary.additional_properties if s.summary else {}
        result.append({
            "snapshot_id": str(s.snapshot_id),
            "parent_id": str(s.parent_snapshot_id) if s.parent_snapshot_id else None,
            "sequence_number": s.sequence_number,
            "timestamp_ms": s.timestamp_ms,
            "operation": s.summary.operation.value if s.summary else None,
            "step": summary.get("step"),
            "total_records": int(summary.get("total-records", 0)),
            "added_records": int(summary.get("added-records", 0)),
            "deleted_records": int(summary.get("deleted-records", 0)),
            "current": s.snapshot_id == current,
        })
    return result


def duck():
    s3 = urlparse(S3_ENDPOINT)
    con = duckdb.connect()
    con.execute("LOAD httpfs")
    con.execute("LOAD iceberg")
    con.execute(
        f"CREATE SECRET i6_s3 (TYPE s3, KEY_ID '{ACCESS_KEY}', SECRET '{SECRET_KEY}', REGION '{REGION}', "
        f"ENDPOINT '{s3.netloc}', URL_STYLE 'path', USE_SSL false)"
    )
    con.execute(f"ATTACH 'warehouse' AS lake (TYPE iceberg, ENDPOINT '{REST_URI}', AUTHORIZATION_TYPE 'none')")
    return con


AGGREGATE_SQL = """
SELECT category,
       count(*) AS total_orders,
       sum(quantity) AS total_quantity,
       sum(quantity * price) AS total_revenue
FROM lake.shop.orders {at}
GROUP BY category
ORDER BY category
"""


def duckdb_query(snapshot_id=None):
    at = f"AT (VERSION => {int(snapshot_id)})" if snapshot_id is not None else ""
    return AGGREGATE_SQL.format(at=at).strip()


def duckdb_aggregates(snapshot_id=None):
    con = duck()
    try:
        return to_rows(con.execute(duckdb_query(snapshot_id)).fetch_arrow_table())
    finally:
        con.close()


def duckdb_snapshots():
    con = duck()
    try:
        rows = con.execute(
            "SELECT sequence_number, snapshot_id, timestamp_ms, manifest_list FROM iceberg_snapshots(lake.shop.orders) ORDER BY sequence_number"
        ).fetchall()
        return [
            {"sequence_number": r[0], "snapshot_id": str(r[1]), "timestamp": str(r[2]), "manifest_list": r[3]}
            for r in rows
        ]
    finally:
        con.close()
