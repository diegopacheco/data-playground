import time

import bench
import db
from catalog import document, load_products, variants
from embed import BATCH_SIZE, DIM, MODEL_NAME, chunk_text, embed_documents, embed_passages, embed_query, to_pg

SAMPLE_QUERIES = ["gear for running", "something to read", "keep my feet dry", "cook a steak"]


def timed(steps, name, fn):
    start = time.perf_counter()
    out = fn()
    steps.append({"step": name, "seconds": round(time.perf_counter() - start, 3)})
    print(f"{name}: {steps[-1]['seconds']}s", flush=True)
    return out


def load_catalog(conn, steps):
    products = timed(steps, "load catalog from orders.csv", load_products)
    vectors, chunks = timed(steps, "chunk and embed products", lambda: embed_documents([document(p) for p in products]))
    counts = {p["id"]: len(chunk_text(document(p))) for p in products}

    def upsert():
        with conn.cursor() as cur:
            cur.executemany(db.UPSERT_PRODUCT, [
                (p["id"], p["name"], p["category"], p["description"], p["orders"], p["revenue"], counts[p["id"]], to_pg(v))
                for p, v in zip(products, vectors)])

    timed(steps, "upsert products", upsert)
    return products, chunks


def load_variants(conn, products, steps):
    items = variants(products)

    def embed_and_upsert():
        with conn.cursor() as cur:
            for i in range(0, len(items), BATCH_SIZE * 4):
                batch = items[i:i + BATCH_SIZE * 4]
                vectors = embed_passages([t for _, _, t in batch])
                cur.executemany(db.UPSERT_VARIANT, [(vid, pid, t, to_pg(v)) for (vid, pid, t), v in zip(batch, vectors)])

    timed(steps, f"embed and upsert {len(items)} variants in batches", embed_and_upsert)
    conn.execute("ANALYZE variants")
    conn.execute("ANALYZE products")
    return len(items)


def sample_searches(conn):
    out = []
    for q in SAMPLE_QUERIES:
        hits = db.rows(conn, db.VECTOR_SEARCH, {"q": to_pg(embed_query(q)), "category": None, "k": 3})
        out.append({"query": q, "top": [f"{h['name']} ({h['category']}) {h['score']:.3f}" for h in hits]})
        print(q, "->", out[-1]["top"], flush=True)
    return out


def main():
    steps = []
    with db.connect() as conn:
        db.init_schema(conn)
        products, chunks = load_catalog(conn, steps)
        variant_count = load_variants(conn, products, steps)
        result = timed(steps, "build hnsw indexes and benchmark exact scan vs hnsw", lambda: bench.run(conn))
        for m in result["modes"]:
            print(f"{m['index'] or m['mode']} ef_search={m['ef_search']} recall@{result['k']}={m['recall']} avg={m['avg_ms']}ms plan={m['plan']}", flush=True)
        sizes = db.rows(conn, "SELECT relname AS name, pg_size_pretty(pg_relation_size(oid)) AS size FROM pg_class "
                              "WHERE relname IN ('products', 'variants', 'variants_embedding_hnsw', 'products_embedding_hnsw') ORDER BY relname")
        db.save_results(conn, {
            "model": MODEL_NAME,
            "dim": DIM,
            "batch_size": BATCH_SIZE,
            "products": len(products),
            "chunks": chunks,
            "variants": variant_count,
            "steps": steps,
            "sizes": sizes,
            "bench": result,
            "samples": sample_searches(conn),
        })
    print("pipeline done", flush=True)


if __name__ == "__main__":
    main()
