import os
import pyarrow as pa
import pyarrow.csv as pv
from pyiceberg.partitioning import PartitionSpec, PartitionField
from pyiceberg.schema import Schema
from pyiceberg.transforms import IdentityTransform
from pyiceberg.types import NestedField, LongType, StringType, IntegerType, DoubleType, TimestamptzType
import lakekeeper
from lake import catalog, NAMESPACE, TABLE

ORDERS = os.path.join(os.path.dirname(__file__), "..", "data", "orders.csv")
FIRST_BATCH = 150
S3_ENDPOINT = os.environ.get("S3_ENDPOINT", "http://localhost:26300")
S3_ACCESS_KEY = os.environ.get("S3_ACCESS_KEY", "q4admin")
S3_SECRET_KEY = os.environ.get("S3_SECRET_KEY", "q4password")

SCHEMA = Schema(
    NestedField(1, "order_id", LongType(), required=True),
    NestedField(2, "customer", StringType(), required=True),
    NestedField(3, "product", StringType(), required=True),
    NestedField(4, "category", StringType(), required=True),
    NestedField(5, "quantity", IntegerType(), required=True),
    NestedField(6, "price", DoubleType(), required=True),
    NestedField(7, "ts", TimestamptzType(), required=True),
)

SPEC = PartitionSpec(PartitionField(source_id=4, field_id=1000, transform=IdentityTransform(), name="category"))


def read_orders():
    data = pv.read_csv(ORDERS)
    return pa.table({
        "order_id": data["order_id"].cast(pa.int64()),
        "customer": data["customer"],
        "product": data["product"],
        "category": data["category"],
        "quantity": data["quantity"].cast(pa.int32()),
        "price": data["price"].cast(pa.float64()),
        "ts": data["ts"].cast(pa.timestamp("us", tz="UTC")),
    }, schema=SCHEMA.as_arrow())


def setup_catalog():
    print(f"bootstrap: {'done now' if lakekeeper.bootstrap() else 'already bootstrapped'}")
    warehouse, created = lakekeeper.ensure_warehouse(S3_ENDPOINT, S3_ACCESS_KEY, S3_SECRET_KEY)
    print(f"warehouse {warehouse['name']} {warehouse['warehouse-id']}: {'created' if created else 'already exists'}")


def recreate_table(cat):
    cat.create_namespace_if_not_exists(NAMESPACE)
    if cat.table_exists(TABLE):
        cat.purge_table(TABLE)
    return cat.create_table(TABLE, schema=SCHEMA, partition_spec=SPEC)


def main():
    setup_catalog()
    orders = read_orders()
    table = recreate_table(catalog())
    for batch in (orders.slice(0, FIRST_BATCH), orders.slice(FIRST_BATCH)):
        table.append(batch)
        snapshot = table.current_snapshot()
        print(f"append {batch.num_rows} rows: snapshot {snapshot.snapshot_id} total-records={snapshot.summary['total-records']}")
    print(f"metadata: {table.metadata_location}")


if __name__ == "__main__":
    main()
