import json
import os
import time

import psycopg

MODES = {
    "any": ("|||", "%(q)s"),
    "all": ("&&&", "%(q)s"),
    "phrase": ("###", "%(q)s"),
    "fuzzy": ("|||", "%(q)s::pdb.fuzzy(2)"),
}

SEARCH = """
SELECT id, name, category, price, description,
       pdb.score(id) AS score,
       {snippet} AS snippet,
       pdb.agg('{{"terms": {{"field": "category"}}}}') OVER () AS facets
FROM products
WHERE name {op} {name_q} OR description {op} {desc_q}
ORDER BY pdb.score(id) DESC, id
LIMIT %(k)s
"""

MATCHED_NAMES = """
SELECT name FROM products WHERE name {op} {name_q} OR description {op} {desc_q}
"""

TOTALS = """
SELECT count(*) AS orders, sum(quantity) AS items, sum(amount) AS revenue, min(ts) AS first, max(ts) AS last
FROM orders WHERE {scope}
"""

BY_CATEGORY = """
SELECT category, count(*) AS orders, sum(quantity) AS items, sum(amount) AS revenue
FROM orders WHERE {scope}
GROUP BY category ORDER BY revenue DESC
"""

TOP_PRODUCTS = """
SELECT product, count(*) AS orders, sum(quantity) AS items, sum(amount) AS revenue
FROM orders WHERE {scope}
GROUP BY product ORDER BY revenue DESC LIMIT 5
"""

BY_DAY = """
SELECT day, count(*) AS orders, sum(amount) AS revenue
FROM orders WHERE {scope}
GROUP BY day ORDER BY day
"""

ALL_ORDERS = "order_id @@@ pdb.all()"
PRODUCT_ORDERS = "product === %(names)s::text[]"


def connect():
    return psycopg.connect(
        host=os.environ.get("PGHOST", "localhost"),
        port=os.environ.get("PGPORT", "26400"),
        dbname="shop", user="shop", password="shop", autocommit=True,
    )


def rows(conn, sql, params=None):
    cur = conn.execute(sql, params)
    names = [c.name for c in cur.description]
    return [dict(zip(names, r)) for r in cur.fetchall()]


def predicate(mode):
    op, q = MODES.get(mode, MODES["any"])
    name_q = q if mode == "fuzzy" else f"{q}::text::pdb.boost(2)"
    return {"op": op, "name_q": name_q, "desc_q": q}


def facet_buckets(value):
    data = json.loads(value) if isinstance(value, str) else value
    return data["buckets"]


def search(conn, q, mode, k):
    parts = predicate(mode)
    snippet = "NULL" if mode == "fuzzy" else "pdb.snippet(description)"
    start = time.perf_counter()
    hits = rows(conn, SEARCH.format(snippet=snippet, **parts), {"q": q, "k": k})
    ms = (time.perf_counter() - start) * 1000
    buckets = facet_buckets(hits[0]["facets"]) if hits else []
    results = [{
        "id": h["id"], "name": h["name"], "category": h["category"], "price": float(h["price"]),
        "score": round(float(h["score"]), 4), "snippet": h["snippet"] or h["description"],
    } for h in hits]
    facets = [{"category": b["key"], "count": b["doc_count"]} for b in buckets]
    return {"query": q, "mode": mode if mode in MODES else "any", "ms": round(ms, 2),
            "total": sum(f["count"] for f in facets), "facets": facets, "results": results}


def matched_names(conn, q, mode):
    return [r["name"] for r in rows(conn, MATCHED_NAMES.format(**predicate(mode)), {"q": q})]


def money(value):
    return float(value) if value is not None else 0.0


def analytics(conn, q, mode):
    params = {}
    scope = ALL_ORDERS
    names = None
    if q:
        names = matched_names(conn, q, mode)
        scope = PRODUCT_ORDERS
        params = {"names": names or [""]}
    start = time.perf_counter()
    totals = rows(conn, TOTALS.format(scope=scope), params)[0]
    by_category = rows(conn, BY_CATEGORY.format(scope=scope), params)
    top = rows(conn, TOP_PRODUCTS.format(scope=scope), params)
    by_day = rows(conn, BY_DAY.format(scope=scope), params)
    ms = (time.perf_counter() - start) * 1000
    plan = [r[0] for r in conn.execute("EXPLAIN " + BY_CATEGORY.format(scope=scope), params).fetchall()]
    return {
        "query": q, "products": names, "ms": round(ms, 2),
        "totals": {"orders": totals["orders"], "items": totals["items"] or 0, "revenue": money(totals["revenue"]),
                   "first": totals["first"].isoformat() if totals["first"] else None,
                   "last": totals["last"].isoformat() if totals["last"] else None},
        "by_category": [{**r, "revenue": money(r["revenue"])} for r in by_category],
        "top_products": [{**r, "revenue": money(r["revenue"])} for r in top],
        "by_day": [{"day": r["day"].isoformat(), "orders": r["orders"], "revenue": money(r["revenue"])} for r in by_day],
        "plan": plan,
    }
