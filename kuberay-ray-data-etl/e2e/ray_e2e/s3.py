import json
from typing import Any

import pyarrow.parquet as pq
from pyarrow import fs

from ray_e2e import config
from ray_e2e.truth import Aggregate, Key


class Bucket:
    def __init__(self) -> None:
        self.fs = fs.S3FileSystem(
            access_key=config.ACCESS_KEY,
            secret_key=config.SECRET_KEY,
            endpoint_override=config.S3_ENDPOINT,
            scheme="http",
            region="us-east-1",
        )

    def path(self, key: str) -> str:
        return f"{config.BUCKET}/{key}"

    def keys(self, prefix: str) -> list[str]:
        selector = fs.FileSelector(self.path(prefix), recursive=True, allow_not_found=True)
        start = len(config.BUCKET) + 1
        return [i.path[start:] for i in self.fs.get_file_info(selector) if i.type == fs.FileType.File]

    def text(self, key: str) -> str:
        with self.fs.open_input_stream(self.path(key)) as stream:
            return stream.read().decode()

    def batches(self, prefix: str, marker: str) -> set[str]:
        return {k.split("/")[1] for k in self.keys(prefix) if k.count("/") == 2 and k.endswith("/" + marker)}

    def ready(self) -> set[str]:
        return self.batches("input", "_READY")

    def committed(self) -> set[str]:
        return self.batches("output", "_SUCCESS")

    def marker(self, batch_id: str) -> dict[str, Any]:
        return json.loads(self.text(f"input/{batch_id}/_READY"))

    def commit(self, batch_id: str) -> dict[str, Any]:
        return json.loads(self.text(f"output/{batch_id}/_SUCCESS"))

    def input_events(self, batch_id: str) -> list[dict[str, Any]]:
        events = []
        for key in self.marker(batch_id)["files"]:
            events.extend(json.loads(line) for line in self.text(key).splitlines() if line)
        return events

    def output_event_ids(self, batch_id: str) -> list[str]:
        table = pq.read_table(self.path(f"output/{batch_id}/events"), filesystem=self.fs, columns=["event_id"])
        return [str(i) for i in table["event_id"].to_pylist()]

    def output_aggregates(self, batch_id: str) -> dict[Key, Aggregate]:
        rows = pq.read_table(self.path(f"output/{batch_id}/aggregates"), filesystem=self.fs).to_pylist()
        return {(r["batch_id"], r["category"]): Aggregate(r["events"], r["amount_cents"], r["max_amount_cents"]) for r in rows}
