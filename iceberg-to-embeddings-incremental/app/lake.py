import csv
import os
from pathlib import Path

import pyarrow as pa
from pyiceberg.catalog import load_catalog
from pyiceberg.expressions import In
from pyiceberg.partitioning import PartitionField, PartitionSpec
from pyiceberg.schema import Schema
from pyiceberg.transforms import IdentityTransform
from pyiceberg.types import LongType, NestedField, StringType

REST_URI = os.environ.get("REST_URI", "http://localhost:30702")
S3_ENDPOINT = os.environ.get("S3_ENDPOINT", "http://localhost:30700")
DATA = Path(__file__).resolve().parent.parent / "data"
NAMESPACE = "library"
TABLE = f"{NAMESPACE}.documents"
COLUMNS = ["id", "category", "text"]

SCHEMA = Schema(
    NestedField(1, "id", LongType(), required=True),
    NestedField(2, "category", StringType(), required=True),
    NestedField(3, "text", StringType(), required=True),
    identifier_field_ids=[1],
)
SPEC = PartitionSpec(PartitionField(source_id=2, field_id=1000, transform=IdentityTransform(), name="category"))
ARROW_SCHEMA = pa.schema([
    pa.field("id", pa.int64(), nullable=False),
    pa.field("category", pa.string(), nullable=False),
    pa.field("text", pa.string(), nullable=False),
])


def catalog():
    return load_catalog(
        "rest",
        type="rest",
        uri=REST_URI,
        **{
            "s3.endpoint": S3_ENDPOINT,
            "s3.access-key-id": "s8admin",
            "s3.secret-access-key": "s8password",
            "s3.region": "us-east-1",
        },
    )


def create_table():
    cat = catalog()
    cat.create_namespace_if_not_exists(NAMESPACE)
    return cat.create_table(TABLE, schema=SCHEMA, partition_spec=SPEC)


def load_table():
    return catalog().load_table(TABLE)


def read_csv(name):
    with open(DATA / name, newline="") as f:
        return [{**row, "id": int(row["id"])} for row in csv.DictReader(f)]


def to_arrow(rows):
    return pa.Table.from_pylist(rows, schema=ARROW_SCHEMA)


def append(table, rows):
    table.append(to_arrow(rows))


def upsert(table, rows):
    table.upsert(to_arrow(rows))


def delete(table, rows):
    table.delete(In("id", [row["id"] for row in rows]))


def table_rows(table, snapshot_id):
    return int(table.snapshot_by_id(snapshot_id).summary.additional_properties.get("total-records", 0))


def snapshots(table):
    result = []
    for s in table.snapshots():
        props = s.summary.additional_properties
        result.append({
            "snapshot_id": str(s.snapshot_id),
            "parent_id": str(s.parent_snapshot_id) if s.parent_snapshot_id else None,
            "sequence_number": s.sequence_number,
            "operation": s.summary.operation.value,
            "added_files": int(props.get("added-data-files", 0)),
            "deleted_files": int(props.get("deleted-data-files", 0)),
            "added_records": int(props.get("added-records", 0)),
            "deleted_records": int(props.get("deleted-records", 0)),
            "total_records": int(props.get("total-records", 0)),
        })
    return result
