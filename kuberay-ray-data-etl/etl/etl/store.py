import json
from collections.abc import Iterable
from dataclasses import asdict, dataclass

from pyarrow import fs

from etl.config import Settings

READY = "_READY"
SUCCESS = "_SUCCESS"


@dataclass(frozen=True)
class Ready:
    batch_id: str
    files: tuple[str, ...]
    events: int
    ready_at_ms: int

    @classmethod
    def parse(cls, text: str) -> "Ready":
        raw = json.loads(text)
        return cls(raw["batch_id"], tuple(raw["files"]), int(raw["events"]), int(raw["ready_at_ms"]))


@dataclass(frozen=True)
class Commit:
    batch_id: str
    ready_at_ms: int
    started_at_ms: int
    committed_at_ms: int
    rows: int

    def to_json(self) -> str:
        return json.dumps(asdict(self))


def batches_with(keys: Iterable[str], marker: str) -> set[str]:
    return {key.split("/")[1] for key in keys if key.count("/") == 2 and key.endswith("/" + marker)}


def pending_batches(input_keys: Iterable[str], output_keys: Iterable[str]) -> list[str]:
    return sorted(batches_with(input_keys, READY) - batches_with(output_keys, SUCCESS))


def s3(settings: Settings) -> fs.FileSystem:
    return fs.S3FileSystem(
        access_key=settings.access_key,
        secret_key=settings.secret_key,
        endpoint_override=settings.endpoint,
        scheme="http",
        region="us-east-1",
        allow_bucket_creation=True,
    )


class Store:
    def __init__(self, filesystem: fs.FileSystem, bucket: str) -> None:
        self.fs = filesystem
        self.bucket = bucket

    def path(self, key: str) -> str:
        return f"{self.bucket}/{key}"

    def ensure_bucket(self) -> None:
        self.fs.create_dir(self.bucket, recursive=True)

    def keys(self, prefix: str) -> list[str]:
        selector = fs.FileSelector(self.path(prefix), recursive=True, allow_not_found=True)
        start = len(self.bucket) + 1
        return [info.path[start:] for info in self.fs.get_file_info(selector) if info.type == fs.FileType.File]

    def pending(self) -> list[str]:
        return pending_batches(self.keys("input"), self.keys("output"))

    def ready(self, batch_id: str) -> Ready:
        return Ready.parse(self.read_text(f"input/{batch_id}/{READY}"))

    def read_text(self, key: str) -> str:
        with self.fs.open_input_stream(self.path(key)) as stream:
            return stream.read().decode()

    def write_text(self, key: str, text: str) -> None:
        with self.fs.open_output_stream(self.path(key)) as stream:
            stream.write(text.encode())

    def clear(self, prefix: str) -> None:
        self.fs.delete_dir_contents(self.path(prefix), missing_dir_ok=True)
