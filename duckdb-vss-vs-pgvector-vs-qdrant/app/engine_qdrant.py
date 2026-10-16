import http.client
import json
import subprocess
import time
from config import PORTS, DIM, K, M, EF_CONSTRUCTION, BUCKET, BUILD_THREADS

COLLECTION = "/collections/items"
MATCH = {"must": [{"key": "bucket", "match": {"value": BUCKET}}]}


class Qdrant:
    name = "qdrant"
    label = "Qdrant"
    parameters = {"m": "hnsw_config.m", "ef_construction": "hnsw_config.ef_construct", "ef_search": "params.hnsw_ef"}
    deployment = "client/server, REST and JSON over HTTP keep-alive"

    def __init__(self):
        self.http = http.client.HTTPConnection("127.0.0.1", PORTS["qdrant"])
        self.ef = None

    def call(self, method, path, body=None):
        self.http.request(method, path, None if body is None else json.dumps(body), {"Content-Type": "application/json"})
        response = self.http.getresponse()
        payload = json.loads(response.read())
        if response.status >= 400:
            raise RuntimeError(f"qdrant {method} {path} {response.status} {payload}")
        return payload["result"] if "result" in payload else payload

    def version(self):
        return f"Qdrant {self.call('GET', '/')['version']}"

    def info(self):
        return self.call("GET", COLLECTION)

    def build(self, vectors, buckets):
        self.http.request("DELETE", COLLECTION)
        self.http.getresponse().read()
        self.call("PUT", COLLECTION, {
            "vectors": {"size": DIM, "distance": "Euclid"},
            "hnsw_config": {"m": M, "ef_construct": EF_CONSTRUCTION, "max_indexing_threads": BUILD_THREADS},
            "optimizers_config": {"indexing_threshold": 0, "default_segment_number": 1},
        })
        self.call("PUT", COLLECTION + "/index?wait=true", {"field_name": "bucket", "field_schema": "integer"})
        for start in range(0, len(vectors), 1000):
            stop = min(start + 1000, len(vectors))
            self.call("PUT", COLLECTION + "/points?wait=true", {"batch": {
                "ids": list(range(start, stop)),
                "vectors": vectors[start:stop].tolist(),
                "payloads": [{"bucket": int(b)} for b in buckets[start:stop]],
            }})
        started = time.perf_counter()
        self.call("PATCH", COLLECTION, {"optimizers_config": {"indexing_threshold": 10000}})
        info = self.info()
        for _ in range(240):
            if info["status"] == "green" and info["indexed_vectors_count"] >= len(vectors):
                break
            time.sleep(0.25)
            info = self.info()
        else:
            raise RuntimeError(f"qdrant hnsw index not built in time: {info['status']} {info['indexed_vectors_count']}")
        seconds = time.perf_counter() - started
        links, storage = self.disk("vector_index"), self.disk("vector_storage")
        return {
            "build_seconds": seconds,
            "index_bytes": links + storage,
            "index_size_source": f"du of the indexed segment: vector_index {links} bytes of compressed links plus vector_storage {storage} bytes",
            "indexed_rows": info["indexed_vectors_count"],
            "state": f"status {info['status']}, {info['segments_count']} segments, {BUILD_THREADS} indexing threads",
        }

    def disk(self, folder):
        command = f"cd /qdrant/storage/collections/items/0/segments && for s in */vector_index; do du -sb ${{s%/*}}/{folder}; done | awk '{{s += $1}} END {{print s}}'"
        return int(subprocess.run(["podman", "exec", "s9-qdrant", "sh", "-c", command], capture_output=True, text=True, check=True).stdout)

    def set_ef(self, ef):
        self.ef = ef

    def query(self, vector, extra):
        body = {"query": vector.tolist(), "limit": K, "params": {"hnsw_ef": self.ef}, "with_payload": False}
        return [p["id"] for p in self.call("POST", COLLECTION + "/points/query", body | extra)["points"]]

    def search(self, vector):
        return self.query(vector, {})

    def filtered_variants(self):
        return [("filter inside the query, payload index on bucket", lambda: None)]

    def search_filtered(self, vector):
        return self.query(vector, {"filter": MATCH})

    def plan(self, vector, filtered):
        config = self.info()["config"]
        keys = ("hnsw_config", "optimizer_config", "quantization_config")
        return json.dumps({k: config[k] for k in keys}, indent=1)
