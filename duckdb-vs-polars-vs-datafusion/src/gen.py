import sys
from pathlib import Path
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.csv as pcsv
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
FACTOR = 50000
DAYS = 365
SUPPLIERS = ["Acme", "Globex", "Initech", "Umbrella", "Stark"]


def load_base():
    t = pcsv.read_csv(DATA / "orders.csv", convert_options=pcsv.ConvertOptions(column_types={"ts": pa.string()}))
    ts = pc.strptime(pc.utf8_slice_codeunits(t["ts"], 0, 19), format="%Y-%m-%dT%H:%M:%S", unit="us")
    cents = pc.cast(pc.round(pc.multiply(t["price"], 100)), pa.int64())
    return pa.table({
        "order_id": pc.cast(t["order_id"], pa.int64()),
        "customer": t["customer"],
        "product": t["product"],
        "category": t["category"],
        "quantity": pc.cast(t["quantity"], pa.int64()),
        "price_cents": cents,
        "ts": ts,
    })


def expand(base, factor):
    n = base.num_rows
    batch_rows = n * 1000
    writer = pq.ParquetWriter(DATA / "orders.parquet", base.schema, compression="zstd")
    for start in range(0, factor, 1000):
        copies = range(start, min(start + 1000, factor))
        ks = pa.array([k for k in copies for _ in range(n)], pa.int64())
        idx = pa.array([i for _ in copies for i in range(n)], pa.int64())
        chunk = base.take(idx)
        shift = pa.array([(k % DAYS) * 86400000000 for k in copies for _ in range(n)], pa.duration("us"))
        chunk = chunk.set_column(0, "order_id", pc.add(pc.multiply(ks, 100000), chunk["order_id"]))
        chunk = chunk.set_column(6, "ts", pc.add(chunk["ts"], shift))
        writer.write_table(chunk, row_group_size=batch_rows)
    writer.close()


def products(base):
    names = sorted(set(base["product"].to_pylist()))
    pq.write_table(pa.table({
        "product_id": pa.array(range(1, len(names) + 1), pa.int64()),
        "product": names,
        "supplier": [SUPPLIERS[i % len(SUPPLIERS)] for i in range(len(names))],
    }), DATA / "products.parquet", compression="zstd")


def main():
    factor = int(sys.argv[1]) if len(sys.argv) > 1 else FACTOR
    base = load_base()
    products(base)
    expand(base, factor)
    meta = pq.ParquetFile(DATA / "orders.parquet").metadata
    print(f"orders.parquet rows={meta.num_rows} row_groups={meta.num_row_groups} size_mb={(DATA / 'orders.parquet').stat().st_size / 1e6:.1f}")


if __name__ == "__main__":
    main()
