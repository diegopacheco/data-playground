import lance
import numpy as np

COLUMN = "embedding"
INDEX = {"index_type": "IVF_PQ", "num_partitions": 256, "num_sub_vectors": 4}
SEARCH = {"nprobes": 20, "refine_factor": 10}
RESULT_COLUMNS = ["order_id", "product", "category", "_distance"]


def build_index(path):
    lance.dataset(str(path)).create_index(COLUMN, replace=True, **INDEX)


def nearest(path, query, k, use_index=True):
    spec = {"column": COLUMN, "q": np.asarray(query, np.float32), "k": k, "use_index": use_index}
    if use_index:
        spec.update(SEARCH)
    return lance.dataset(str(path)).to_table(columns=RESULT_COLUMNS, nearest=spec)


def exact(vectors, query, k):
    distances = ((vectors - np.asarray(query, np.float32)) ** 2).sum(axis=1)
    top = np.argpartition(distances, k)[:k]
    return top[np.argsort(distances[top])]


def recall(found_ids, exact_rows):
    expected = {int(r) + 1 for r in exact_rows}
    return len(expected & set(found_ids)) / len(expected)
