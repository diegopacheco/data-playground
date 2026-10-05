import os

import pyarrow.compute as pc
from dagster import AssetCheckResult, Definitions, MaterializeResult, asset, asset_check, in_process_executor

from i36_pipeline import lake, revenue

ORDERS_CSV = os.environ.get("ORDERS_CSV", "/app/data/orders.csv")


def materialized(name, data):
    snapshot = lake.write_table(name, data)
    return MaterializeResult(
        metadata={"rows": data.num_rows, "iceberg_table": f"{lake.NAMESPACE}.{name}", "snapshot_id": str(snapshot)}
    )


@asset(group_name="iceberg")
def raw_orders():
    return materialized("raw_orders", revenue.load_raw(ORDERS_CSV))


@asset(group_name="iceberg", deps=[raw_orders])
def clean_orders():
    raw = lake.read_table("raw_orders").scan().to_arrow()
    return materialized("clean_orders", revenue.clean(raw))


@asset(group_name="iceberg", deps=[clean_orders])
def revenue_by_category():
    orders = lake.read_table("clean_orders").scan().to_arrow()
    return materialized("revenue_by_category", revenue.revenue_by_category(orders))


@asset_check(asset=clean_orders)
def clean_orders_valid():
    orders = lake.read_table("clean_orders").scan().to_arrow()
    ids = orders["order_id"]
    unique = pc.count_distinct(ids).as_py() == len(ids)
    positive = pc.all(pc.greater(orders["revenue"], 0)).as_py()
    return AssetCheckResult(passed=bool(unique and positive), metadata={"rows": len(ids), "unique_ids": unique})


@asset_check(asset=revenue_by_category)
def revenue_matches_orders():
    orders = lake.read_table("clean_orders").scan().to_arrow()
    totals = lake.read_table("revenue_by_category").scan().to_arrow()
    expected = round(pc.sum(orders["revenue"]).as_py(), 2)
    actual = round(pc.sum(totals["revenue"]).as_py(), 2)
    return AssetCheckResult(passed=abs(expected - actual) < 0.01, metadata={"expected": expected, "actual": actual})


defs = Definitions(
    assets=[raw_orders, clean_orders, revenue_by_category],
    asset_checks=[clean_orders_valid, revenue_matches_orders],
    executor=in_process_executor,
)
