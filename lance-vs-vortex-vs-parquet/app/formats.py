import shutil
from pathlib import Path

import lance
import pyarrow as pa
import pyarrow.dataset as pds
import pyarrow.parquet as pq
import vortex as vx
import vortex.expr as ve

FILTER_CATEGORY = "electronics"
FILTER_MIN_QUANTITY = 3
PROJECTION = ["order_id", "price"]


def size_of(path):
    path = Path(path)
    if path.is_dir():
        return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
    return path.stat().st_size


def remove(path):
    path = Path(path)
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()


class Parquet:
    name = "parquet"
    ext = "parquet"
    settings = "pyarrow, zstd, default row groups"

    def write(self, table, path):
        pq.write_table(table, path, compression="zstd")

    def scan(self, path):
        return pq.read_table(path)

    def filter(self, path):
        return pq.read_table(path, columns=PROJECTION,
                             filters=[("category", "=", FILTER_CATEGORY), ("quantity", ">=", FILTER_MIN_QUANTITY)])

    def take(self, path, indices):
        return pds.dataset(path, format="parquet").take(pa.array(indices, pa.int64()))


class Lance:
    name = "lance"
    ext = "lance"
    settings = "pylance, default file version and encodings"

    def write(self, table, path):
        lance.write_dataset(table, str(path), mode="overwrite")

    def scan(self, path):
        return lance.dataset(str(path)).to_table()

    def filter(self, path):
        return lance.dataset(str(path)).to_table(
            columns=PROJECTION, filter=f"category = '{FILTER_CATEGORY}' AND quantity >= {FILTER_MIN_QUANTITY}")

    def take(self, path, indices):
        return lance.dataset(str(path)).take(indices)


class Vortex:
    name = "vortex"
    ext = "vortex"
    settings = "vortex-data, default write options"

    def write(self, table, path):
        vx.io.write(table, str(path))

    def scan(self, path):
        return vx.open(str(path)).to_arrow().read_all()

    def filter(self, path):
        predicate = (ve.column("category") == FILTER_CATEGORY) & (ve.column("quantity") >= FILTER_MIN_QUANTITY)
        return vx.open(str(path)).to_arrow(projection=PROJECTION, expr=predicate).read_all()

    def take(self, path, indices):
        rows = vx.open(str(path)).scan(indices=vx.array(pa.array(indices, pa.uint64()))).read_all()
        return pa.Table.from_struct_array(rows.to_arrow_array())


FORMATS = [Parquet(), Lance(), Vortex()]
