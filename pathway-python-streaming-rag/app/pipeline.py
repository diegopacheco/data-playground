import uuid

import pathway as pw

WINDOW_SECONDS = 60


class OrderSchema(pw.Schema):
    order_id: str
    region: str
    amount: int
    ts: int


class RegionSchema(pw.Schema):
    region: str = pw.column_definition(primary_key=True)
    name: str
    tax_pct: int


def file_orders(folder):
    return pw.io.csv.read(folder, schema=OrderSchema, mode="streaming", object_pattern="*.csv", autocommit_duration_ms=200)


def kafka_orders(brokers, topic):
    settings = {
        "bootstrap.servers": brokers,
        "group.id": f"t4-pathway-{uuid.uuid4()}",
        "auto.offset.reset": "earliest",
    }
    return pw.io.kafka.read(settings, topic=topic, schema=OrderSchema, format="json", autocommit_duration_ms=200)


def regions(folder):
    return pw.io.csv.read(folder, schema=RegionSchema, mode="streaming", object_pattern="*.csv", autocommit_duration_ms=200)


def enrich(orders, regions_table):
    return orders.join(regions_table, orders.region == regions_table.region).select(
        orders.order_id,
        orders.region,
        orders.amount,
        orders.ts,
        regions_table.name,
        gross=orders.amount * (100 + regions_table.tax_pct) // 100,
    )


def windows(enriched):
    return enriched.windowby(
        pw.this.ts,
        window=pw.temporal.tumbling(duration=WINDOW_SECONDS, origin=0),
        instance=pw.this.region,
    ).reduce(
        region=pw.this._pw_instance,
        window_start=pw.this._pw_window_start,
        orders=pw.reducers.count(),
        revenue=pw.reducers.sum(pw.this.amount),
        gross=pw.reducers.sum(pw.this.gross),
        max_amount=pw.reducers.max(pw.this.amount),
    )


def region_totals(enriched):
    return enriched.groupby(pw.this.region).reduce(
        pw.this.region,
        name=pw.reducers.any(pw.this.name),
        orders=pw.reducers.count(),
        revenue=pw.reducers.sum(pw.this.amount),
        gross=pw.reducers.sum(pw.this.gross),
    )


def build(orders_folder, regions_folder, brokers, topic):
    orders = pw.Table.concat_reindex(file_orders(orders_folder), kafka_orders(brokers, topic))
    enriched = enrich(orders, regions(regions_folder))
    return windows(enriched), region_totals(enriched)
