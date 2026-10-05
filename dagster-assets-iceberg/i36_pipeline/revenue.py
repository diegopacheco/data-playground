import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.csv as pcsv

RAW_TYPES = {
    "order_id": pa.int64(),
    "customer": pa.string(),
    "product": pa.string(),
    "category": pa.string(),
    "quantity": pa.int64(),
    "price": pa.float64(),
    "ts": pa.string(),
}


def load_raw(path):
    return pcsv.read_csv(path, convert_options=pcsv.ConvertOptions(column_types=RAW_TYPES))


def round2(values):
    return pa.array([round(v, 2) for v in values.to_pylist()], pa.float64())


def first_occurrence(ids):
    seen = set()
    keep = []
    for oid in ids:
        keep.append(oid not in seen)
        seen.add(oid)
    return pa.array(keep)


def clean(raw):
    valid = pc.and_kleene(pc.greater(raw["quantity"], 0), pc.greater(raw["price"], 0))
    rows = raw.filter(pc.and_kleene(valid, pc.is_valid(raw["category"])))
    rows = rows.filter(first_occurrence(rows["order_id"].to_pylist()))
    category = pc.utf8_lower(pc.utf8_trim_whitespace(rows["category"]))
    rows = rows.set_column(rows.schema.get_field_index("category"), "category", category)
    revenue = round2(pc.multiply(pc.cast(rows["quantity"], pa.float64()), rows["price"]))
    return rows.append_column("revenue", revenue)


def revenue_by_category(orders):
    grouped = orders.group_by("category").aggregate(
        [("order_id", "count"), ("quantity", "sum"), ("revenue", "sum")]
    )
    table = pa.table(
        {
            "category": grouped["category"],
            "orders": grouped["order_id_count"],
            "units": grouped["quantity_sum"],
            "revenue": round2(grouped["revenue_sum"]),
        }
    )
    return table.sort_by([("revenue", "descending")])
