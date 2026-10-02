import csv
import os

from trino import query

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")


def quote(text):
    return "'" + text.replace("'", "''") + "'"


def values(rows):
    return ",\n".join(
        f"({r['product_id']}, {quote(r['product'])}, {quote(r['category'])}, {quote(r['supplier'])}, DECIMAL '{r['cost']}')"
        for r in rows
    )


def main():
    with open(os.path.join(DATA, "products.csv"), newline="") as f:
        rows = list(csv.DictReader(f))
    query("CREATE SCHEMA IF NOT EXISTS iceberg.lake")
    query("DROP TABLE IF EXISTS iceberg.lake.products")
    query("CREATE TABLE iceberg.lake.products (product_id integer, product varchar, category varchar, supplier varchar, cost decimal(10,2)) WITH (format = 'PARQUET')")
    query("INSERT INTO iceberg.lake.products VALUES\n" + values(rows))
    _, count = query("SELECT count(*) FROM iceberg.lake.products")
    print(f"iceberg.lake.products rows: {count[0][0]}")


if __name__ == "__main__":
    main()
