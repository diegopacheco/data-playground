import os

from pyiceberg.catalog.sql import SqlCatalog

LAKE_DIR = os.environ.get("LAKE_DIR", "/app/lake")
NAMESPACE = "shop"


def catalog():
    os.makedirs(f"{LAKE_DIR}/warehouse", exist_ok=True)
    cat = SqlCatalog(
        "lake",
        uri=f"sqlite:///{LAKE_DIR}/catalog.db",
        warehouse=f"file://{LAKE_DIR}/warehouse",
    )
    cat.create_namespace_if_not_exists(NAMESPACE)
    return cat


def write_table(name, data):
    cat = catalog()
    table = cat.create_table_if_not_exists(f"{NAMESPACE}.{name}", schema=data.schema)
    table.overwrite(data)
    return table.current_snapshot().snapshot_id


def read_table(name):
    return catalog().load_table(f"{NAMESPACE}.{name}")
