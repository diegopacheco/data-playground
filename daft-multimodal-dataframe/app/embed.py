import os
from functools import cache

from fastembed import TextEmbedding

MODEL = "BAAI/bge-small-en-v1.5"
DIM = 384
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "
CACHE = os.environ.get("FASTEMBED_CACHE_PATH", "/models")


@cache
def model():
    return TextEmbedding(MODEL, cache_dir=CACHE, threads=2)


def passages(texts):
    return [v.tolist() for v in model().embed(texts)]


def query(text):
    return next(model().embed([QUERY_PREFIX + text])).tolist()


def warm():
    query("warm up")
