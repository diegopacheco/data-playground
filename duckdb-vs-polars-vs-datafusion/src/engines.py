from pathlib import Path
from queries import SQL

DATA = Path(__file__).resolve().parent.parent / "data"
ORDERS = str(DATA / "orders.parquet")
PRODUCTS = str(DATA / "products.parquet")


def open_duckdb():
    import duckdb
    con = duckdb.connect()
    con.execute(f"CREATE VIEW orders AS SELECT * FROM read_parquet('{ORDERS}')")
    con.execute(f"CREATE VIEW products AS SELECT * FROM read_parquet('{PRODUCTS}')")
    return lambda q: con.execute(SQL[q]).fetchall()


def open_polars():
    import polars as pl
    from polars_queries import QUERIES

    def run(q):
        frame = QUERIES[q](pl.scan_parquet(ORDERS), pl.scan_parquet(PRODUCTS)).collect()
        return frame.rows()
    return run


def open_datafusion():
    from datafusion import SessionContext
    ctx = SessionContext()
    ctx.register_parquet("orders", ORDERS)
    ctx.register_parquet("products", PRODUCTS)

    def run(q):
        table = ctx.sql(SQL[q]).to_arrow_table()
        return [tuple(r.values()) for r in table.to_pylist()]
    return run


ENGINES = {"duckdb": open_duckdb, "polars": open_polars, "datafusion": open_datafusion}


def version(engine):
    from importlib.metadata import version as v
    return v(engine)
