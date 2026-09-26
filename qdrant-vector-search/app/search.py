import time

import embed
import qdrant

PREFETCH = 20
MODES = ("semantic", "keyword", "hybrid")


def build_filter(category=None, price_min=None, price_max=None, min_rating=None, in_stock=False, exclude_id=None):
    must = []
    if category:
        must.append({"key": "category", "match": {"value": category}})
    price = {k: v for k, v in (("gte", price_min), ("lte", price_max)) if v is not None}
    if price:
        must.append({"key": "price", "range": price})
    if min_rating is not None:
        must.append({"key": "rating", "range": {"gte": min_rating}})
    if in_stock:
        must.append({"key": "in_stock", "match": {"value": True}})
    result = {}
    if must:
        result["must"] = must
    if exclude_id is not None:
        result["must_not"] = [{"has_id": [exclude_id]}]
    return result or None


def request(query, using, flt, limit):
    body = {"query": query, "using": using, "limit": limit, "with_payload": True}
    if flt:
        body["filter"] = flt
    return body


def text_request(mode, text, flt, limit):
    if mode == "semantic":
        return request(embed.query_dense(text), "dense", flt, limit)
    if mode == "keyword":
        return request(embed.query_sparse(text), "bm25", flt, limit)
    return {
        "prefetch": [
            request(embed.query_dense(text), "dense", flt, PREFETCH),
            request(embed.query_sparse(text), "bm25", flt, PREFETCH),
        ],
        "query": {"fusion": "rrf"},
        "limit": limit,
        "with_payload": True,
    }


def recommend_request(point_id, flt, limit):
    return request({"recommend": {"positive": [point_id]}}, "dense", flt, limit)


def shorten(value):
    if isinstance(value, dict):
        return {k: shorten(v) for k, v in value.items()}
    if isinstance(value, list) and len(value) > 6 and all(isinstance(x, (int, float)) for x in value):
        return [round(x, 4) if isinstance(x, float) else x for x in value[:4]] + [f"... {len(value)} numbers"]
    if isinstance(value, list):
        return [shorten(v) for v in value]
    return value


def run(body):
    start = time.perf_counter()
    empty = body.get("using") == "bm25" and not body["query"]["indices"]
    points = [] if empty else qdrant.query(body)
    return {
        "query_ms": round((time.perf_counter() - start) * 1000, 2),
        "request": shorten(body),
        "results": [{"id": p["id"], "score": round(p["score"], 4), **p["payload"]} for p in points],
    }


def search(text, mode, flt, limit):
    start = time.perf_counter()
    body = text_request(mode, text, flt, limit)
    embed_ms = round((time.perf_counter() - start) * 1000, 2)
    return {"query": text, "mode": mode, "embed_ms": embed_ms, **run(body)}


def recommend(point_id, flt, limit):
    return {"mode": "recommend", "positive": point_id, "embed_ms": 0, **run(recommend_request(point_id, flt, limit))}
