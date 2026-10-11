import pandas as pd
import pandera.pandas as pa

COLUMNS = ["order_id", "customer_id", "order_ts", "region", "product", "quantity", "unit_price", "currency"]
REGIONS = ["NORTH", "SOUTH", "EAST", "WEST"]
PRODUCTS = ["keyboard", "mouse", "monitor", "laptop", "headset", "webcam", "dock", "cable"]
MAX_QUANTITY = 100
MAX_PRICE = 10000
FRESHNESS = pd.Timedelta(hours=24)


def bronze_contract():
    return pa.DataFrameSchema(
        {name: pa.Column(str, nullable=True) for name in COLUMNS},
        strict=True,
        name="bronze: raw structure",
        checks=[pa.Check(lambda df: len(df) > 0, error="batch has at least one row")],
    )


def silver_contract(extracted_at, promoted_ids):
    extracted = pd.Timestamp(extracted_at)
    return pa.DataFrameSchema(
        {
            "order_id": pa.Column(str, unique=True, checks=[
                pa.Check.str_matches(r"^ORD-\d{6}$"),
                pa.Check(lambda s: ~s.isin(promoted_ids), error="order_id not already promoted"),
            ]),
            "customer_id": pa.Column(str, pa.Check.str_matches(r"^C-\d{4}$")),
            "order_ts": pa.Column("datetime64[ns]", pa.Check(lambda s: s <= extracted, error="order_ts not after extraction")),
            "region": pa.Column(str, pa.Check.isin(REGIONS)),
            "product": pa.Column(str, pa.Check.isin(PRODUCTS)),
            "quantity": pa.Column("int64", pa.Check.in_range(1, MAX_QUANTITY)),
            "unit_price": pa.Column("float64", pa.Check.in_range(0.01, MAX_PRICE)),
            "currency": pa.Column(str, pa.Check.isin(["USD"])),
        },
        coerce=True,
        strict=True,
        name="silver: typed orders",
        checks=[pa.Check(lambda df: extracted - df["order_ts"].max() <= FRESHNESS, error="freshness: newest order within 24h of extraction")],
    )


def gold_contract(silver_orders, silver_revenue):
    return pa.DataFrameSchema(
        {
            "day": pa.Column(str, pa.Check.str_matches(r"^\d{4}-\d{2}-\d{2}$")),
            "region": pa.Column(str, pa.Check.isin(REGIONS)),
            "orders": pa.Column("int64", pa.Check.ge(1)),
            "units": pa.Column("int64", pa.Check.ge(1)),
            "revenue": pa.Column("float64", pa.Check.ge(0)),
        },
        coerce=True,
        strict=True,
        unique=["day", "region"],
        name="gold: daily revenue per region",
        checks=[
            pa.Check(lambda df: int(df["orders"].sum()) == silver_orders, error="orders reconcile with silver"),
            pa.Check(lambda df: abs(float(df["revenue"].sum()) - silver_revenue) < 0.005, error="revenue reconciles with silver"),
        ],
    )


def catalog(schema):
    entries = [
        {"column": "*", "check": "column_in_dataframe", "label": "every contract column is present"},
        {"column": "*", "check": "column_in_schema", "label": "no column outside the contract"},
    ]
    if schema.unique:
        entries.append({"column": "*", "check": "duplicates", "label": f"unique on {', '.join(schema.unique)}"})
    for name, col in schema.columns.items():
        entries.append({"column": name, "check": "dtype", "label": f"type {col.dtype}"})
        if not col.nullable:
            entries.append({"column": name, "check": "not_nullable", "label": "not null"})
        if col.unique:
            entries.append({"column": name, "check": "field_uniqueness", "label": "unique"})
        entries += [{"column": name, "check": c.error, "label": c.error} for c in col.checks]
    entries += [{"column": "*", "check": c.error, "label": c.error} for c in schema.checks]
    return entries


def describe():
    return {
        "bronze": {"name": bronze_contract().name, "checks": catalog(bronze_contract())},
        "silver": {"name": silver_contract("2026-01-01", []).name, "checks": catalog(silver_contract("2026-01-01", []))},
        "gold": {"name": gold_contract(0, 0.0).name, "checks": catalog(gold_contract(0, 0.0))},
    }
