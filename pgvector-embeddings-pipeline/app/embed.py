from pathlib import Path

import numpy as np
from fastembed import TextEmbedding

MODEL_NAME = "BAAI/bge-small-en-v1.5"
DIM = 384
BATCH_SIZE = 256
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "
CACHE = Path(__file__).resolve().parent.parent / ".models"

_model = None


def model():
    global _model
    if _model is None:
        _model = TextEmbedding(MODEL_NAME, cache_dir=str(CACHE))
    return _model


def chunk_text(text, max_words=24, overlap=6):
    words = text.split()
    if len(words) <= max_words:
        return [text]
    step = max_words - overlap
    return [" ".join(words[i:i + max_words]) for i in range(0, len(words) - overlap, step)]


def embed_passages(texts):
    return np.array(list(model().embed(texts, batch_size=BATCH_SIZE)), dtype=np.float32)


def embed_query(text):
    return embed_passages([QUERY_PREFIX + text])[0]


def embed_documents(documents):
    chunks = [chunk_text(d) for d in documents]
    flat = [c for cs in chunks for c in cs]
    vectors = embed_passages(flat)
    out, i = [], 0
    for cs in chunks:
        mean = vectors[i:i + len(cs)].mean(axis=0)
        out.append(mean / np.linalg.norm(mean))
        i += len(cs)
    return out, sum(len(cs) for cs in chunks)


def to_pg(vector):
    return "[" + ",".join(f"{x:.6f}" for x in vector) + "]"
