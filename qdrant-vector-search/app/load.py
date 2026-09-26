import csv
import time
from pathlib import Path

import embed
import qdrant

CSV = Path(__file__).resolve().parent.parent / "data" / "products.csv"
BATCH = 16
INDEXES = {"category": "keyword", "brand": "keyword", "price": "float", "rating": "float", "in_stock": "bool"}


def read_products():
    with CSV.open(newline="") as f:
        return [
            {
                "id": int(r["id"]),
                "name": r["name"],
                "category": r["category"],
                "brand": r["brand"],
                "price": float(r["price"]),
                "rating": float(r["rating"]),
                "in_stock": r["in_stock"] == "true",
                "description": r["description"],
            }
            for r in csv.DictReader(f)
        ]


def document(product):
    return f"{product['name']} by {product['brand']}. {product['description']}"


def ensure_collection():
    if qdrant.call("GET", qdrant.collection("/exists"))["result"]["exists"]:
        return False
    qdrant.call("PUT", qdrant.collection(), {
        "vectors": {"dense": {"size": embed.DIM, "distance": "Cosine"}},
        "sparse_vectors": {"bm25": {"modifier": "idf"}},
    })
    return True


def ensure_indexes():
    for field, schema in INDEXES.items():
        qdrant.call("PUT", qdrant.collection("/index?wait=true"), {"field_name": field, "field_schema": schema})


def to_points(products):
    dense, sparse = embed.passages([document(p) for p in products])
    return [
        {"id": p["id"], "vector": {"dense": d, "bm25": s}, "payload": {k: v for k, v in p.items() if k != "id"}}
        for p, d, s in zip(products, dense, sparse)
    ]


def upsert(points):
    for i in range(0, len(points), BATCH):
        qdrant.call("PUT", qdrant.collection("/points?wait=true"), {"points": points[i:i + BATCH]})


def timed(label, fn, *args):
    start = time.perf_counter()
    result = fn(*args)
    print(f"{label:<22} {(time.perf_counter() - start) * 1000:8.1f} ms", flush=True)
    return result


def main():
    products = timed("read csv", read_products)
    created = timed("ensure collection", ensure_collection)
    timed("ensure payload indexes", ensure_indexes)
    points = timed("embed dense + bm25", to_points, products)
    timed("upsert points", upsert, points)
    count = qdrant.call("POST", qdrant.collection("/points/count"), {"exact": True})["result"]["count"]
    print(f"collection {'created' if created else 'reused'}, csv rows {len(products)}, points {count}", flush=True)
    if count != len(products):
        raise SystemExit(f"point count {count} differs from csv rows {len(products)}")


if __name__ == "__main__":
    main()
