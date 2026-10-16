import numpy as np
from config import SEED, ROWS, DIM, CLUSTERS, SPREAD, QUERIES, BUCKETS


def clustered(rng, centers, count):
    picked = centers[rng.integers(0, len(centers), count)]
    return (picked + SPREAD * rng.standard_normal((count, DIM))).astype(np.float32)


def generate():
    rng = np.random.default_rng(SEED)
    centers = rng.standard_normal((CLUSTERS, DIM))
    vectors = clustered(rng, centers, ROWS)
    queries = clustered(rng, centers, QUERIES)
    buckets = rng.integers(0, BUCKETS, ROWS).astype(np.int32)
    return vectors, queries, buckets


def exact_top(vectors, ids, queries, k):
    base = vectors.astype(np.float64)
    norms = (base * base).sum(axis=1)
    top = []
    for start in range(0, len(queries), 100):
        q = queries[start:start + 100].astype(np.float64)
        distance = norms[None, :] - 2.0 * (q @ base.T)
        nearest = np.argpartition(distance, k, axis=1)[:, :k]
        order = np.take_along_axis(distance, nearest, axis=1).argsort(axis=1)
        top.extend(ids[np.take_along_axis(nearest, order, axis=1)].tolist())
    return top


def literal(vector):
    return "[" + ",".join(map(str, vector.tolist())) + "]"
