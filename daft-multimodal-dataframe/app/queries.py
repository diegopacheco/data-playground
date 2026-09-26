import base64
import io
import json
import re
import time

import daft
import numpy as np
from daft import col, lit

import embed
from features import EMBEDDING
from pipeline import PARQUET, RUN

COLUMNS = ["id", "name", "category", "brand", "price", "sale_price", "discount_pct", "campaign", "rating", "in_stock",
           "width", "height", "dominant_color", "dominant_hex", "brightness", "saturation", "thumbnail_png"]

PRESETS = [
    {"id": "bright-red-under-50", "title": "Bright red items under $50",
     "params": {"color": "red", "min_brightness": "70", "max_price": "50"}},
    {"id": "dark-photos", "title": "Dark product photos",
     "params": {"max_brightness": "65"}},
    {"id": "warm-winter-in-blue", "title": "Something to stay warm in freezing winter, in blue",
     "params": {"q": "stay warm in freezing winter", "color": "blue"}},
    {"id": "promo-in-stock", "title": "On a color promotion and in stock",
     "params": {"promo": "true", "in_stock": "true"}},
]


def conditions(params):
    result = []
    if params.get("color"):
        result.append(col("dominant_color") == params["color"])
    if params.get("category"):
        result.append(col("category") == params["category"])
    if params.get("max_price"):
        result.append(col("price") <= float(params["max_price"]))
    if params.get("min_brightness"):
        result.append(col("brightness") >= float(params["min_brightness"]))
    if params.get("max_brightness"):
        result.append(col("brightness") <= float(params["max_brightness"]))
    if params.get("promo") == "true":
        result.append(col("discount_pct") > 0)
    if params.get("in_stock") == "true":
        result.append(col("in_stock"))
    return result


def plan_text(df):
    buffer = io.StringIO()
    df.explain(show_all=True, file=buffer)
    return re.sub(r"Tensor\(\[[^\]]*\]\)", f"Tensor([{embed.DIM} query floats])", buffer.getvalue())


def thumbnails(rows):
    for row in rows:
        row["thumbnail"] = "data:image/png;base64," + base64.b64encode(row.pop("thumbnail_png")).decode()
    return rows


def products(params, limit=50):
    start = time.perf_counter()
    df = daft.read_parquet(str(PARQUET))
    for condition in conditions(params):
        df = df.where(condition)
    columns = list(COLUMNS)
    text = params.get("q", "").strip()
    if text:
        vector = lit(np.array(embed.query(text), dtype=np.float32)).cast(EMBEDDING)
        df = df.with_column("similarity", col("embedding").cosine_similarity(vector).round(4)).sort("similarity", desc=True)
        columns.append("similarity")
    else:
        df = df.sort("id")
    df = df.select(*columns).limit(limit)
    plan = plan_text(df)
    rows = thumbnails(df.to_pylist())
    return {"params": params, "rows": rows, "count": len(rows), "plan": plan,
            "elapsed_ms": round((time.perf_counter() - start) * 1000, 1)}


def groupby():
    start = time.perf_counter()
    df = (daft.read_parquet(str(PARQUET))
          .groupby("category", "dominant_color")
          .agg(col("id").count().alias("products"),
               col("price").sum().round(2).alias("total_price"),
               col("sale_price").sum().round(2).alias("total_sale_price"),
               col("brightness").mean().round(1).alias("avg_brightness"))
          .sort(["category", "dominant_color"]))
    plan = plan_text(df)
    rows = df.to_pylist()
    return {"rows": rows, "plan": plan, "elapsed_ms": round((time.perf_counter() - start) * 1000, 1)}


def info():
    df = daft.read_parquet(str(PARQUET))
    run = json.loads(RUN.read_text())
    return {
        "daft_version": daft.__version__,
        "runner": daft.get_or_infer_runner_type(),
        "model": embed.MODEL,
        "rows": df.count_rows(),
        "schema": [{"name": f.name, "dtype": str(f.dtype)} for f in df.schema()],
        "presets": PRESETS,
        "pipeline": run,
    }
