from datetime import datetime
import polars as pl
from queries import START, END

REVENUE = (pl.col("quantity") * pl.col("price_cents")).alias("revenue_cents")


def q1(orders, products):
    return (orders.group_by("category")
            .agg(pl.len().alias("orders"), pl.col("quantity").sum(), REVENUE.sum())
            .sort("category"))


def q2(orders, products):
    return (orders.group_by("customer").agg(REVENUE.sum())
            .sort(["revenue_cents", "customer"], descending=[True, False]).head(10))


def q3(orders, products):
    return (orders.filter((pl.col("ts") >= datetime.fromisoformat(START)) & (pl.col("ts") < datetime.fromisoformat(END)))
            .group_by(pl.col("ts").dt.date().alias("day"), "category")
            .agg(REVENUE.sum())
            .sort(["day", "category"]))


def q4(orders, products):
    return (orders.join(products, on="product")
            .group_by("supplier")
            .agg(pl.len().alias("orders"), pl.col("customer").n_unique().alias("customers"), REVENUE.sum())
            .sort("supplier"))


QUERIES = {"q1": q1, "q2": q2, "q3": q3, "q4": q4}
