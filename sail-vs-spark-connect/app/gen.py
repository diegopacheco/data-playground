import os
import random
import shutil
from pathlib import Path
import pyarrow as pa
import pyarrow.parquet as pq

DATA = Path(os.environ.get("DATA_DIR", "/data"))
ROWS = int(os.environ.get("ROWS", "5000000"))
FILES = 8
SEED = 2026
PRODUCTS = 500
CUSTOMERS = 100000
FIRST_DAY = 20089
DAYS = 730
CATEGORIES = ["books", "clothing", "electronics", "garden", "home", "sports", "toys", "beauty"]
SUPPLIERS = [f"supplier-{i:02d}" for i in range(1, 13)]
REGIONS = ["north", "south", "east", "west", "central", "islands"]
CHANNELS = ["web", "store", "mobile"]
STATUSES = ["completed", "returned", "cancelled"]
STATUS_WEIGHTS = [85, 8, 7]


def products(rng):
    ids = list(range(1, PRODUCTS + 1))
    return pa.table({
        "product_id": pa.array(ids, pa.int32()),
        "product_name": [f"product-{i:03d}" for i in ids],
        "category": [rng.choice(CATEGORIES) for _ in ids],
        "supplier": [rng.choice(SUPPLIERS) for _ in ids],
        "list_price_cents": pa.array([rng.randint(199, 49999) for _ in ids], pa.int64()),
    })


def orders_chunk(rng, first_id, n, prices):
    product = rng.choices(range(1, PRODUCTS + 1), k=n)
    return pa.table({
        "order_id": pa.array(range(first_id, first_id + n), pa.int64()),
        "order_date": pa.array([FIRST_DAY + d for d in rng.choices(range(DAYS), k=n)], pa.int32()).cast(pa.date32()),
        "customer_id": pa.array(rng.choices(range(1, CUSTOMERS + 1), k=n), pa.int32()),
        "product_id": pa.array(product, pa.int32()),
        "region": rng.choices(REGIONS, k=n),
        "channel": rng.choices(CHANNELS, k=n),
        "status": rng.choices(STATUSES, weights=STATUS_WEIGHTS, k=n),
        "quantity": pa.array(rng.choices(range(1, 6), k=n), pa.int32()),
        "price_cents": pa.array([prices[p] for p in product], pa.int64()),
    })


def main():
    rng = random.Random(SEED)
    dim = products(rng)
    DATA.mkdir(parents=True, exist_ok=True)
    pq.write_table(dim, DATA / "products.parquet", compression="zstd")
    prices = dict(zip(dim["product_id"].to_pylist(), dim["list_price_cents"].to_pylist()))
    out = DATA / "orders"
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir()
    per_file = ROWS // FILES
    for i in range(FILES):
        n = per_file if i < FILES - 1 else ROWS - per_file * (FILES - 1)
        pq.write_table(orders_chunk(rng, i * per_file + 1, n, prices), out / f"part-{i:05d}.parquet", compression="zstd")
        print(f"wrote part {i + 1}/{FILES} ({n} rows)")
    size = sum(f.stat().st_size for f in out.iterdir())
    print(f"orders: {ROWS} rows in {FILES} files, {size / 1e6:.1f} MB; products: {PRODUCTS} rows")


if __name__ == "__main__":
    main()
