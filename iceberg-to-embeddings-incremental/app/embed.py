from pathlib import Path

import numpy as np
from fastembed import TextEmbedding

MODEL_NAME = "BAAI/bge-small-en-v1.5"
DIM = 384
BATCH_SIZE = 16
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "
CACHE = Path(__file__).resolve().parent.parent / ".models"
STATS = {"rows": 0, "model_calls": 0}

_model = None


def model():
    global _model
    if _model is None:
        _model = TextEmbedding(MODEL_NAME, cache_dir=str(CACHE))
    return _model


def embed_passages(texts):
    vectors = []
    for start in range(0, len(texts), BATCH_SIZE):
        batch = texts[start:start + BATCH_SIZE]
        STATS["rows"] += len(batch)
        STATS["model_calls"] += 1
        vectors.extend(model().embed(batch, batch_size=BATCH_SIZE))
    return np.array(vectors, dtype=np.float32).reshape(-1, DIM)


def embed_query(text):
    return embed_passages([QUERY_PREFIX + text])[0]


def to_pg(vector):
    return "[" + ",".join(f"{x:.8f}" for x in vector) + "]"
