import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.csv as pcsv
import pyarrow.orc as orc
import pyarrow.parquet as pq
import fastavro

from dataset import SCHEMA

PROJECTED = "quantity"

AVRO_SCHEMA = fastavro.parse_schema({
    "type": "record",
    "name": "Order",
    "fields": [
        {"name": "order_id", "type": "long"},
        {"name": "customer", "type": "string"},
        {"name": "product", "type": "string"},
        {"name": "category", "type": "string"},
        {"name": "quantity", "type": "long"},
        {"name": "price", "type": "double"},
        {"name": "ts", "type": {"type": "long", "logicalType": "timestamp-millis"}},
    ],
})

AVRO_PROJECTION = fastavro.parse_schema({
    "type": "record",
    "name": "Order",
    "fields": [{"name": PROJECTED, "type": "long"}],
})


class Csv:
    format = "csv"

    def __init__(self, codec):
        self.codec = codec
        self.ext = "csv"

    def write(self, table, path):
        pcsv.write_csv(table, path)

    def read(self, path):
        return pcsv.read_csv(path, convert_options=pcsv.ConvertOptions(column_types=SCHEMA))

    def project(self, path):
        options = pcsv.ConvertOptions(column_types=SCHEMA, include_columns=[PROJECTED])
        return pcsv.read_csv(path, convert_options=options)


class Parquet:
    format = "parquet"

    def __init__(self, codec):
        self.codec = codec
        self.ext = "parquet"

    def write(self, table, path):
        pq.write_table(table, path, compression=self.codec)

    def read(self, path):
        return pq.read_table(path)

    def project(self, path):
        return pq.read_table(path, columns=[PROJECTED])


class Orc:
    format = "orc"

    def __init__(self, codec):
        self.codec = codec
        self.ext = "orc"

    def write(self, table, path):
        orc.write_table(table, path, compression=self.codec)

    def read(self, path):
        return orc.read_table(path)

    def project(self, path):
        return orc.read_table(path, columns=[PROJECTED])


class Avro:
    format = "avro"

    def __init__(self, codec):
        self.codec = codec
        self.ext = "avro"

    def write(self, table, path):
        with open(path, "wb") as out:
            fastavro.writer(out, AVRO_SCHEMA, table.to_pylist(), codec=self.codec)

    def read(self, path):
        with open(path, "rb") as src:
            return list(fastavro.reader(src))

    def project(self, path):
        with open(path, "rb") as src:
            return list(fastavro.reader(src, reader_schema=AVRO_PROJECTION))


VARIANTS = [
    Csv("none"),
    Parquet("none"),
    Parquet("snappy"),
    Parquet("zstd"),
    Orc("uncompressed"),
    Orc("snappy"),
    Orc("zstd"),
    Avro("null"),
    Avro("snappy"),
    Avro("zstandard"),
]


def label(variant):
    return f"{variant.format}-{variant.codec}"


def aggregate(data):
    if isinstance(data, pa.Table):
        return aggregate_table(data)
    return aggregate_records(data)


def aggregate_table(table):
    revenue = pc.multiply(pc.cast(table.column("quantity"), pa.float64()), table.column("price"))
    grouped = pa.table({
        "category": table.column("category"),
        "quantity": table.column("quantity"),
        "revenue": revenue,
    }).group_by("category").aggregate([
        ("quantity", "count"), ("quantity", "sum"), ("revenue", "sum"),
    ])
    return {
        row["category"]: summary(row["quantity_count"], row["quantity_sum"], row["revenue_sum"])
        for row in grouped.to_pylist()
    }


def aggregate_records(records):
    totals = {}
    for r in records:
        t = totals.setdefault(r["category"], [0, 0, 0.0])
        t[0] += 1
        t[1] += r["quantity"]
        t[2] += r["quantity"] * r["price"]
    return {c: summary(*t) for c, t in totals.items()}


def summary(orders, quantity, revenue):
    return {"orders": orders, "quantity": quantity, "revenue": round(revenue, 2)}


def projected_sum(data):
    if isinstance(data, pa.Table):
        return pc.sum(data.column(PROJECTED)).as_py()
    return sum(r[PROJECTED] for r in data)


def row_count(data):
    return data.num_rows if isinstance(data, pa.Table) else len(data)
