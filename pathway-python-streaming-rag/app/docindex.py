import os

import numpy as np
import pathway as pw
from pathway.stdlib.indexing import BruteForceKnn, BruteForceKnnMetricKind, DataIndex

import embedder


class QuerySchema(pw.Schema):
    query: str
    k: int = pw.column_definition(default_value=3)


@pw.udf
def embed(text: str) -> np.ndarray:
    return np.array(embedder.embed(text), dtype=np.float64)


@pw.udf
def doc_name(metadata: pw.Json) -> str:
    return os.path.basename(metadata["path"].as_str())


@pw.udf
def ranked(names: tuple, scores: tuple) -> pw.Json:
    pairs = sorted(zip(names, scores), key=lambda pair: (-pair[1], pair[0]))
    return pw.Json([{"doc": name, "score": round(float(score), 6), "similarity": round(1.0 + float(score), 6)} for name, score in pairs])


def documents(folder):
    files = pw.io.fs.read(folder, format="plaintext_by_file", mode="streaming", with_metadata=True, object_pattern="*.md", autocommit_duration_ms=200)
    docs = files.select(doc=doc_name(pw.this._metadata), text=pw.this.data)
    return docs.filter(pw.this.text.str.strip() != "")


def index(docs):
    inner = BruteForceKnn(
        docs.text,
        None,
        dimensions=embedder.DIMENSIONS,
        reserved_space=1024,
        metric=BruteForceKnnMetricKind.COS,
        embedder=embed,
    )
    return DataIndex(docs, inner)


def serve(docs, host, port):
    queries, respond = pw.io.http.rest_connector(
        host=host,
        port=port,
        route="/v1/retrieve",
        schema=QuerySchema,
        methods=("POST",),
        autocommit_duration_ms=50,
        delete_completed_queries=False,
    )
    matches = index(docs).query_as_of_now(queries.query, number_of_matches=queries.k)
    results = matches.select(
        result=ranked(pw.coalesce(pw.right.doc, ()), pw.coalesce(pw.right._pw_index_reply_score, ()))
    )
    respond(results)
