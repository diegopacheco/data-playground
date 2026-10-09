import statistics
import time

from embed import embed_query, to_pg

K = 10
EF_SEARCH = [10, 40, 100, 200]
INDEX_CONFIGS = [(16, 64), (32, 200)]
QUERIES = [
    "gear for running",
    "something to read",
    "warm clothes for winter",
    "kitchen tools for cooking dinner",
    "gift for a small child",
    "listen to music without wires",
    "learn about distributed databases",
    "stay dry when it rains",
    "home workout equipment",
    "brew a morning drink",
    "protect my head while biking",
    "science fiction story",
    "typing on a computer",
    "family game night",
    "comfortable sofa decoration",
    "charge my laptop and phone",
    "track my heart rate",
    "racket sport",
    "light for reading at night",
    "stretching and meditation",
]

TOP_K = "SELECT id FROM variants ORDER BY embedding <=> %s::vector LIMIT %s"


def plan_nodes(plan):
    nodes = [plan["Node Type"] + (f" using {plan['Index Name']}" if "Index Name" in plan else "")]
    for child in plan.get("Plans", []):
        nodes.extend(plan_nodes(child))
    return nodes


def run_query(conn, vector, exact, ef_search):
    with conn.transaction():
        if exact:
            conn.execute("SET LOCAL enable_indexscan = off")
        else:
            conn.execute(f"SET LOCAL hnsw.ef_search = {int(ef_search)}")
        ids = [r[0] for r in conn.execute(TOP_K, (vector, K)).fetchall()]
        explain = conn.execute("EXPLAIN (ANALYZE, FORMAT JSON) " + TOP_K, (vector, K)).fetchone()[0][0]
    return ids, explain["Execution Time"], plan_nodes(explain["Plan"])


def summary(mode, recalls, times, plan):
    return {
        **mode,
        "recall": round(statistics.mean(recalls), 4),
        "per_query_recall": recalls,
        "avg_ms": round(statistics.mean(times), 3),
        "p50_ms": round(statistics.median(times), 3),
        "plan": plan,
    }


def measure(conn, vectors, truth, mode, exact, ef_search):
    recalls, times, plan = [], [], None
    for v, expected in zip(vectors, truth):
        ids, ms, plan = run_query(conn, v, exact, ef_search)
        recalls.append(len(expected & set(ids)) / K)
        times.append(ms)
    return summary(mode, recalls, times, plan)


def build_index(conn, m, ef_construction):
    conn.execute("DROP INDEX IF EXISTS variants_embedding_hnsw")
    conn.execute("SET maintenance_work_mem = '128MB'")
    start = time.perf_counter()
    conn.execute(f"CREATE INDEX variants_embedding_hnsw ON variants USING hnsw (embedding vector_cosine_ops) "
                 f"WITH (m = {int(m)}, ef_construction = {int(ef_construction)})")
    seconds = round(time.perf_counter() - start, 3)
    size = conn.execute("SELECT pg_size_pretty(pg_relation_size('variants_embedding_hnsw'))").fetchone()[0]
    conn.execute("ANALYZE variants")
    return seconds, size


def run(conn):
    vectors = [to_pg(embed_query(q)) for q in QUERIES]
    for v in vectors:
        run_query(conn, v, True, 0)
    truth = [set(run_query(conn, v, True, 0)[0]) for v in vectors]
    modes = [measure(conn, vectors, truth, {"mode": "exact scan", "index": None, "ef_search": None}, True, 0)]
    builds = []
    for m, ef_construction in INDEX_CONFIGS:
        seconds, size = build_index(conn, m, ef_construction)
        label = f"hnsw m={m} ef_construction={ef_construction}"
        builds.append({"index": label, "build_seconds": seconds, "size": size})
        for ef in EF_SEARCH:
            modes.append(measure(conn, vectors, truth, {"mode": "hnsw", "index": label, "ef_search": ef}, False, ef))
    return {"k": K, "queries": QUERIES, "builds": builds, "modes": modes}
