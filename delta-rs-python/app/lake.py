import os
import pyarrow as pa
import pyarrow.compute as pc
from pyarrow import csv
from deltalake import DeltaTable

TABLE_URI = os.environ.get("TABLE_URI", "s3://lake/orders")

STORAGE = {
    "AWS_ENDPOINT_URL": os.environ.get("S3_ENDPOINT", "http://i5-minio:9000"),
    "AWS_ACCESS_KEY_ID": os.environ.get("S3_ACCESS_KEY", "i5admin"),
    "AWS_SECRET_ACCESS_KEY": os.environ.get("S3_SECRET_KEY", "i5password"),
    "AWS_REGION": "us-east-1",
    "AWS_ALLOW_HTTP": "true",
    "AWS_CONDITIONAL_PUT": "etag",
}

SCHEMA = pa.schema([
    ("order_id", pa.int64()),
    ("customer", pa.string()),
    ("product", pa.string()),
    ("category", pa.string()),
    ("quantity", pa.int64()),
    ("price", pa.float64()),
    ("ts", pa.string()),
])


def read_csv(path):
    options = csv.ConvertOptions(column_types=SCHEMA)
    return csv.read_csv(path, convert_options=options).select(SCHEMA.names)


def open_table(version=None):
    return DeltaTable(TABLE_URI, version=version, storage_options=STORAGE)


def revenue_by_category(table):
    data = table.to_pyarrow_table(columns=["category", "quantity", "price"])
    data = data.append_column("revenue", pc.multiply(data["quantity"], data["price"]))
    grouped = data.group_by("category").aggregate([
        ("category", "count"),
        ("quantity", "sum"),
        ("revenue", "sum"),
    ])
    rows = [
        {
            "category": r["category"],
            "total_orders": r["category_count"],
            "total_quantity": r["quantity_sum"],
            "total_revenue": round(r["revenue_sum"], 2),
        }
        for r in grouped.to_pylist()
    ]
    return sorted(rows, key=lambda r: r["category"])


def versions():
    history = sorted(open_table().history(), key=lambda h: h["version"])
    result = []
    for h in history:
        table = open_table(h["version"])
        categories = revenue_by_category(table)
        result.append({
            "version": h["version"],
            "timestamp": h.get("timestamp"),
            "operation": h.get("operation"),
            "parameters": h.get("operationParameters", {}),
            "metrics": h.get("operationMetrics", {}),
            "files": len(table.file_uris()),
            "rows": sum(c["total_orders"] for c in categories),
            "revenue": round(sum(c["total_revenue"] for c in categories), 2),
            "categories": categories,
        })
    return result
