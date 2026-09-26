import io
import json
import os
import time
from pathlib import Path

import daft
from daft import col, lit

import embed
from features import image_features, text_embedding

DATA = Path(os.environ.get("DATA_DIR", "/app/data"))
OUTPUT = Path(os.environ.get("OUTPUT_DIR", "/app/output"))
PARQUET = OUTPUT / "products"
RUN = OUTPUT / "run.json"
THUMBNAIL = 128
DROPPED = ["image_url", "image_bytes", "image", "promo_color"]


def read_products(_):
    return daft.read_csv(str(DATA / "products.csv")).exclude("color", "tone").with_column("image_url", lit(f"file://{DATA}/") + col("image_path"))


def download_images(df):
    return df.with_column("image_bytes", col("image_url").download())


def decode_and_resize(df):
    image = col("image_bytes").decode_image(mode="RGB")
    return (df.with_column("image", image)
              .with_column("width", col("image").image_width())
              .with_column("height", col("image").image_height())
              .with_column("thumbnail", col("image").resize(THUMBNAIL, THUMBNAIL))
              .with_column("thumbnail_png", col("thumbnail").encode_image("PNG")))


def extract_image_features(df):
    return df.select("*", image_features(col("thumbnail")))


def embed_text(df):
    return df.with_column("embedding", text_embedding(col("name") + lit(". ") + col("description")))


def join_promotions(df):
    promotions = daft.read_csv(str(DATA / "promotions.csv")).with_column_renamed("color", "promo_color")
    return (df.join(promotions, left_on="dominant_color", right_on="promo_color", how="left")
              .with_column("discount_pct", col("discount_pct").fill_null(0))
              .with_column("sale_price", (col("price") * (100 - col("discount_pct")) / 100).round(2)))


def finalize(df):
    return df.exclude(*[c for c in DROPPED if c in df.column_names]).sort("id")


STAGES = [
    ("read csv", read_products),
    ("download image bytes", download_images),
    ("decode + resize", decode_and_resize),
    ("image features (udf)", extract_image_features),
    ("text embeddings (batch udf)", embed_text),
    ("join promotions", join_promotions),
]


def lazy_plan():
    df = None
    for _, stage in STAGES:
        df = stage(df)
    buffer = io.StringIO()
    finalize(df).explain(show_all=True, file=buffer)
    return buffer.getvalue()


def run_stages():
    df, timings = None, []
    for name, stage in STAGES:
        start = time.perf_counter()
        df = stage(df).collect()
        timings.append({"stage": name, "ms": round((time.perf_counter() - start) * 1000, 1),
                        "rows": len(df), "columns": len(df.column_names)})
        print(f"{name:<30} {timings[-1]['ms']:>9.1f} ms  rows {len(df)}", flush=True)
    return df, timings


def write(df, timings):
    start = time.perf_counter()
    files = finalize(df).write_parquet(str(PARQUET), write_mode="overwrite").to_pydict()["path"]
    timings.append({"stage": "write parquet", "ms": round((time.perf_counter() - start) * 1000, 1),
                    "rows": len(df), "columns": len(finalize(df).column_names)})
    print(f"{'write parquet':<30} {timings[-1]['ms']:>9.1f} ms  files {len(files)}", flush=True)
    return files


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    embed.warm()
    plan = lazy_plan()
    started = time.perf_counter()
    df, timings = run_stages()
    files = write(df, timings)
    RUN.write_text(json.dumps({
        "daft_version": daft.__version__,
        "runner": daft.get_or_infer_runner_type(),
        "rows": len(df),
        "thumbnail": THUMBNAIL,
        "total_ms": round((time.perf_counter() - started) * 1000, 1),
        "stages": timings,
        "files": [Path(f).name for f in files],
        "plan": plan,
    }, indent=2))
    print(f"wrote {len(df)} rows to {PARQUET}", flush=True)


if __name__ == "__main__":
    main()
