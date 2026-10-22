import os
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.csv as pv
from pyiceberg.expressions import EqualTo
from pyiceberg.partitioning import PartitionSpec, PartitionField
from pyiceberg.schema import Schema
from pyiceberg.transforms import IdentityTransform
from pyiceberg.types import NestedField, LongType, StringType, IntegerType, DoubleType, TimestamptzType
from lake import catalog, NAMESPACE, TABLE

ORDERS = os.path.join(os.path.dirname(__file__), "..", "data", "orders.csv")
FIRST_BATCH = 150

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


def recreate_table(cat):
    cat.create_namespace_if_not_exists(NAMESPACE)
    if cat.table_exists(TABLE):
        cat.purge_table(TABLE)
    return cat.create_table(TABLE, schema=SCHEMA, partition_spec=SPEC)


def doubled_books(table):
    books = table.scan(row_filter=EqualTo("category", "books")).to_arrow()
    index = books.schema.get_field_index("quantity")
    return books.set_column(index, books.schema.field(index), pc.multiply(books["quantity"], pa.scalar(2, pa.int32())))


def report(table, step):
    table.refresh()
    snapshot = table.current_snapshot()
    print(f"{step}: snapshot {snapshot.snapshot_id} op={snapshot.summary.operation.value} rows={table.scan().to_arrow().num_rows}")


def main():
    cat = catalog()
    orders = read_orders()
    table = recreate_table(cat)

    table.append(orders.slice(0, FIRST_BATCH), snapshot_properties={"step": "append-150"})
    report(table, "append-150")

    table.append(orders.slice(FIRST_BATCH), snapshot_properties={"step": "append-50"})
    report(table, "append-50")

    table.delete(EqualTo("quantity", 1), snapshot_properties={"step": "delete-qty-1"})
    report(table, "delete-qty-1")

    table.overwrite(doubled_books(table), overwrite_filter=EqualTo("category", "books"), snapshot_properties={"step": "overwrite-books"})
    report(table, "overwrite-books")


if __name__ == "__main__":
    main()
