METALAKE = "shop_lake"
CATALOG = "shop_pg"
JOB_NAMESPACE = "shop_pipeline"

CATALOG_COMMENT = "Postgres 18 database shop, schemas and tables created through Gravitino"

GROUPS = ["data_engineering", "analytics"]

TAGS = {
    "bronze": "raw data exactly as it landed from the source",
    "silver": "typed, cleaned and free of personal data",
    "gold": "business aggregates ready for reporting",
    "pii": "personal data, restricted access",
}

SCHEMAS = [
    {"name": "raw", "comment": "landing zone for source files", "owner": "data_engineering", "tags": ["bronze"]},
    {"name": "clean", "comment": "cleaned and validated records", "owner": "data_engineering", "tags": ["silver"]},
    {"name": "gold", "comment": "aggregates for analytics", "owner": "analytics", "tags": ["gold"]},
]


def column(name, type_, comment, tags=()):
    return {"name": name, "type": type_, "comment": comment, "tags": list(tags)}


TABLES = [
    {
        "schema": "raw", "name": "raw_orders", "owner": "data_engineering", "tags": ["bronze", "pii"],
        "comment": "orders.csv as landed, one row per csv line",
        "columns": [
            column("order_id", "long", "order identifier from the source"),
            column("customer", "string", "customer name as typed by the shop", ["pii"]),
            column("product", "string", "product name"),
            column("category", "string", "product category"),
            column("quantity", "integer", "units ordered"),
            column("price", "decimal(10,2)", "unit price"),
            column("ts", "timestamp", "order time"),
        ],
    },
    {
        "schema": "clean", "name": "clean_orders", "owner": "data_engineering", "tags": ["silver"],
        "comment": "valid orders with the customer replaced by a sha256 hash and the line amount computed",
        "columns": [
            column("order_id", "long", "order identifier"),
            column("customer_hash", "string", "sha256 of the lowercased customer name"),
            column("product", "string", "trimmed product name"),
            column("category", "string", "lowercased category"),
            column("quantity", "integer", "units ordered, always above zero"),
            column("price", "decimal(10,2)", "unit price, always above zero"),
            column("amount", "decimal(12,2)", "quantity times price"),
            column("ts", "timestamp", "order time"),
        ],
    },
    {
        "schema": "gold", "name": "revenue_by_category", "owner": "analytics", "tags": ["gold"],
        "comment": "revenue, orders and units per category",
        "columns": [
            column("category", "string", "product category"),
            column("orders", "long", "number of orders"),
            column("quantity", "long", "units sold"),
            column("revenue", "decimal(14,2)", "sum of amount"),
        ],
    },
]


def table(schema, name):
    return next(t for t in TABLES if t["schema"] == schema and t["name"] == name)


def full_name(t):
    return f"{CATALOG}.{t['schema']}.{t['name']}"
