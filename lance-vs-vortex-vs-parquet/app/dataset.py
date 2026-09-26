import numpy as np
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.csv as pcsv

DIM = 16
HOUR_MS = 3_600_000

BASE_SCHEMA = pa.schema([
    ("order_id", pa.int64()),
    ("customer", pa.string()),
    ("product", pa.string()),
    ("category", pa.string()),
    ("quantity", pa.int64()),
    ("price", pa.float64()),
    ("ts", pa.timestamp("ms", tz="UTC")),
])

SCHEMA = BASE_SCHEMA.append(pa.field("embedding", pa.list_(pa.float32(), DIM)))


def load_base(path):
    options = pcsv.ConvertOptions(column_types=BASE_SCHEMA)
    return pcsv.read_csv(path, convert_options=options).cast(BASE_SCHEMA)


def product_centers(products, categories):
    names = sorted(set(categories))
    cat_rng = np.random.default_rng(7)
    cat_center = {c: cat_rng.normal(size=DIM) for c in names}
    prod_rng = np.random.default_rng(11)
    pairs = sorted(set(zip(products, categories)))
    return {p: cat_center[c] + prod_rng.normal(scale=0.5, size=DIM) for p, c in pairs}


def embeddings(products, categories, rows):
    centers = product_centers(products, categories)
    base = np.stack([centers[p] for p in products])
    noise = np.random.default_rng(42).normal(scale=0.2, size=(rows, DIM))
    return (base + noise).astype(np.float32)


def expand(base, rows):
    size = base.num_rows
    i = np.arange(rows)
    b, k = i % size, i // size
    quantity = base.column("quantity").to_numpy()[b] + k % 3
    price = np.round(base.column("price").to_numpy()[b] * (100 + k % 7) / 100, 2)
    ts = base.column("ts").cast(pa.int64()).to_numpy()[b] + k * HOUR_MS
    picked = base.take(pa.array(b))
    vectors = embeddings(picked.column("product").to_pylist(), picked.column("category").to_pylist(), rows)
    return pa.table({
        "order_id": pa.array(i + 1, pa.int64()),
        "customer": picked.column("customer"),
        "product": picked.column("product"),
        "category": picked.column("category"),
        "quantity": pa.array(quantity, pa.int64()),
        "price": pa.array(price, pa.float64()),
        "ts": pa.array(ts, pa.int64()).cast(BASE_SCHEMA.field("ts").type),
        "embedding": pa.FixedSizeListArray.from_arrays(pa.array(vectors.ravel()), DIM),
    }, schema=SCHEMA)


def normalize(table):
    return table.select(SCHEMA.names).cast(SCHEMA).combine_chunks()


def checksums(table):
    revenue = pc.multiply(pc.cast(table.column("quantity"), pa.float64()), table.column("price"))
    per_category = pa.table({"category": table.column("category"), "revenue": revenue}).group_by("category").aggregate(
        [("revenue", "count"), ("revenue", "sum")])
    flat = pc.list_flatten(table.column("embedding")) if table.num_rows else pa.array([], pa.float32())
    return {
        "rows": table.num_rows,
        "order_id_sum": pc.sum(table.column("order_id")).as_py() or 0,
        "quantity_sum": pc.sum(table.column("quantity")).as_py() or 0,
        "ts_sum": pc.sum(table.column("ts").cast(pa.int64())).as_py() or 0,
        "text_bytes": sum(pc.sum(pc.binary_length(table.column(c))).as_py() or 0 for c in ("customer", "product", "category")),
        "revenue": {r["category"]: [r["revenue_count"], round(r["revenue_sum"], 2)] for r in per_category.sort_by("category").to_pylist()},
        "embedding_sum": round(pc.sum(pc.cast(flat, pa.float64())).as_py() or 0.0, 3),
    }
