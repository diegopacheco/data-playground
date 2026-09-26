import duckdb
from pyiceberg.catalog import load_catalog
from lakekeeper import LAKEKEEPER_URL, WAREHOUSE

CATALOG_URI = f"{LAKEKEEPER_URL}/catalog"
NAMESPACE = "shop"
TABLE = f"{NAMESPACE}.orders"

REVENUE_SQL = """
SELECT category,
       count(*) AS total_orders,
       sum(quantity) AS total_quantity,
       round(sum(quantity * price), 2) AS total_revenue
FROM lake.shop.orders {at}
GROUP BY category
ORDER BY category
"""


def catalog():
    return load_catalog("lakekeeper", type="rest", uri=CATALOG_URI, warehouse=WAREHOUSE)


def duck():
    con = duckdb.connect()
    con.execute("LOAD httpfs")
    con.execute("LOAD iceberg")
    con.execute(f"ATTACH '{WAREHOUSE}' AS lake (TYPE iceberg, ENDPOINT '{CATALOG_URI}', AUTHORIZATION_TYPE 'none')")
    return con


def revenue_sql(snapshot_id=None):
    at = f"AT (VERSION => {int(snapshot_id)})" if snapshot_id else ""
    return REVENUE_SQL.format(at=at).strip()


def revenue(snapshot_id=None):
    con = duck()
    try:
        rows = con.execute(revenue_sql(snapshot_id)).fetchall()
    finally:
        con.close()
    return [
        {"category": r[0], "total_orders": int(r[1]), "total_quantity": int(r[2]), "total_revenue": float(r[3])}
        for r in rows
    ]


def snapshots(table):
    current = table.current_snapshot().snapshot_id
    result = []
    for s in sorted(table.snapshots(), key=lambda s: s.sequence_number):
        summary = s.summary.additional_properties
        result.append({
            "snapshot_id": str(s.snapshot_id),
            "parent_id": str(s.parent_snapshot_id) if s.parent_snapshot_id else None,
            "sequence_number": s.sequence_number,
            "timestamp_ms": s.timestamp_ms,
            "operation": s.summary.operation.value,
            "added_records": int(summary.get("added-records", 0)),
            "total_records": int(summary.get("total-records", 0)),
            "added_files": int(summary.get("added-data-files", 0)),
            "total_files": int(summary.get("total-data-files", 0)),
            "manifest_list": s.manifest_list,
            "current": s.snapshot_id == current,
        })
    return result


def table_info():
    cat = catalog()
    table = cat.load_table(TABLE)
    metadata = table.metadata
    return {
        "catalog_uri": CATALOG_URI,
        "warehouse": WAREHOUSE,
        "namespaces": [".".join(n) for n in cat.list_namespaces()],
        "tables": [".".join(t) for t in cat.list_tables(NAMESPACE)],
        "table": TABLE,
        "table_uuid": str(metadata.table_uuid),
        "format_version": metadata.format_version,
        "location": metadata.location,
        "metadata_location": table.metadata_location,
        "schema": [{"id": f.field_id, "name": f.name, "type": str(f.field_type), "required": f.required} for f in table.schema().fields],
        "partition_spec": ", ".join(f"{f.transform}({f.name})" for f in table.spec().fields),
        "snapshots": snapshots(table),
    }
