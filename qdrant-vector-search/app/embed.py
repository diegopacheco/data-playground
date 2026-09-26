import os
from functools import cache
from pathlib import Path

from fastembed import SparseTextEmbedding, TextEmbedding

DENSE_MODEL = "BAAI/bge-small-en-v1.5"
SPARSE_MODEL = "Qdrant/bm25"
DIM = 384
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "
CACHE = os.environ.get("FASTEMBED_CACHE_PATH", "/models")


@cache
def dense_model():
    return TextEmbedding(DENSE_MODEL, cache_dir=CACHE, threads=2)


@cache
def sparse_model():
    snapshot = next(Path(CACHE).glob("models--Qdrant--bm25/snapshots/*"), None)
    return SparseTextEmbedding(SPARSE_MODEL, cache_dir=CACHE, specific_model_path=snapshot and str(snapshot))


def to_sparse(embedding):
    return {"indices": embedding.indices.tolist(), "values": embedding.values.tolist()}


def passages(texts):
    dense = [v.tolist() for v in dense_model().embed(texts)]
    sparse = [to_sparse(e) for e in sparse_model().passage_embed(texts)]
    return dense, sparse


def query_dense(text):
    return next(dense_model().embed([QUERY_PREFIX + text])).tolist()


def query_sparse(text):
    return to_sparse(next(sparse_model().query_embed(text)))


def warm():
    passages(["warm up"])
    query_sparse("warm up")
