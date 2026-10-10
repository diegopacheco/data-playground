import pyarrow as pa
import pyarrow.csv as pcsv

SCHEMA = pa.schema([
    ("order_id", pa.int64()),
    ("customer", pa.string()),
    ("product", pa.string()),
    ("category", pa.string()),
    ("quantity", pa.int64()),
    ("price", pa.float64()),
    ("ts", pa.timestamp("ms", tz="UTC")),
])

HOUR_MS = 3_600_000


def load_base(path):
    options = pcsv.ConvertOptions(column_types=SCHEMA)
    return pcsv.read_csv(path, convert_options=options).cast(SCHEMA)


def expand(base, rows):
    size = base.num_rows
    quantity = base.column("quantity").to_pylist()
    price = base.column("price").to_pylist()
    ts = base.column("ts").cast(pa.int64()).to_pylist()
    idx, qty, prc, tms = [], [], [], []
    for i in range(rows):
        b, k = i % size, i // size
        idx.append(b)
        qty.append(quantity[b] + k % 3)
        prc.append(round(price[b] * (100 + k % 7) / 100, 2))
        tms.append(ts[b] + k * HOUR_MS)
    picked = base.take(pa.array(idx))
    return pa.table({
        "order_id": pa.array(range(1, rows + 1), pa.int64()),
        "customer": picked.column("customer"),
        "product": picked.column("product"),
        "category": picked.column("category"),
        "quantity": pa.array(qty, pa.int64()),
        "price": pa.array(prc, pa.float64()),
        "ts": pa.array(tms, pa.int64()).cast(SCHEMA.field("ts").type),
    }, schema=SCHEMA)
