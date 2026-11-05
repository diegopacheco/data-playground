import json
import os
import struct
import subprocess
import sys
import time

import pyarrow as pa
import pyarrow.parquet as pq

from checksums import table_checksums

NIMBLE_BENCH = os.environ.get("NIMBLE_BENCH", "/opt/nimble/nimble_bench")
PARQUET = {"parquet_snappy": "snappy", "parquet_zstd": "zstd"}
FORMATS = ["nimble", "parquet_snappy", "parquet_zstd"]
EXTENSION = {"nimble": "nimble", "parquet_snappy": "parquet", "parquet_zstd": "parquet"}


def file_path(table_dir, name):
    return os.path.join(table_dir, f"{name}.{EXTENSION[name]}")


def load_source(table_dir):
    with pa.OSFile(os.path.join(table_dir, "source.arrow")) as f:
        return pa.ipc.open_file(f).read_all()


def timed(fn, iterations):
    times = []
    result = None
    for _ in range(iterations):
        start = time.perf_counter()
        result = fn()
        times.append((time.perf_counter() - start) * 1000)
    return times, result


def parquet_write(name, table_dir, iterations):
    table = load_source(table_dir)
    path = file_path(table_dir, name)
    times, _ = timed(lambda: pq.write_table(table, path, compression=PARQUET[name]), iterations)
    return {"write_ms": times, "size_bytes": os.path.getsize(path), "rows": table.num_rows, "columns": table.num_columns}


def parquet_scan(name, table_dir, iterations, columns=None):
    path = file_path(table_dir, name)
    read = lambda: pq.ParquetFile(path).read(columns=columns, use_threads=False)
    times, table = timed(read, iterations)
    return {"scan_ms": times, "rows": table.num_rows, "columns": table.num_columns, "checksums": table_checksums(table)}


def parquet_meta(name, table_dir, iterations):
    path = file_path(table_dir, name)

    def read():
        f = pq.ParquetFile(path)
        return f.schema_arrow, f.metadata

    times, (schema, metadata) = timed(read, iterations)
    with open(path, "rb") as f:
        f.seek(-8, os.SEEK_END)
        footer_bytes = struct.unpack("<i", f.read(4))[0]
    return {"meta_ms": times, "columns": len(schema), "footer_bytes": footer_bytes,
            "row_groups": metadata.num_row_groups, "file_bytes": os.path.getsize(path)}


def nimble(*args):
    env = dict(os.environ, LD_LIBRARY_PATH=os.path.join(os.path.dirname(NIMBLE_BENCH), "lib"))
    out = subprocess.run([NIMBLE_BENCH, *map(str, args)], capture_output=True, text=True, env=env)
    if out.returncode != 0:
        raise RuntimeError(f"nimble_bench {' '.join(map(str, args))} failed: {out.stderr.strip()[-2000:]}")
    return json.loads(out.stdout.strip().splitlines()[-1])


def nimble_write(table_dir, iterations):
    return nimble("write", os.path.join(table_dir, "source"), file_path(table_dir, "nimble"), iterations)


def nimble_scan(table_dir, iterations, columns=None):
    args = ["scan", os.path.join(table_dir, "source"), file_path(table_dir, "nimble"), iterations]
    return nimble(*(args + [",".join(columns)] if columns else args))


def nimble_meta(table_dir, iterations):
    return nimble("meta", file_path(table_dir, "nimble"), iterations)


def nimble_dump(table_dir, out_dir):
    return nimble("dump", file_path(table_dir, "nimble"), out_dir)


def run_step(name, action, table_dir, iterations, columns=None):
    if name == "nimble":
        steps = {"write": lambda: nimble_write(table_dir, iterations),
                 "scan": lambda: nimble_scan(table_dir, iterations),
                 "project": lambda: nimble_scan(table_dir, iterations, columns),
                 "meta": lambda: nimble_meta(table_dir, iterations)}
        return steps[action]()
    command = [sys.executable, os.path.abspath(__file__), name, action, table_dir, str(iterations)]
    if columns:
        command.append(",".join(columns))
    out = subprocess.run(command, capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(f"{name} {action} failed: {out.stderr.strip()[-2000:]}")
    return json.loads(out.stdout.strip().splitlines()[-1])


def main(argv):
    name, action, table_dir, iterations = argv[0], argv[1], argv[2], int(argv[3])
    columns = argv[4].split(",") if len(argv) > 4 else None
    steps = {"write": lambda: parquet_write(name, table_dir, iterations),
             "scan": lambda: parquet_scan(name, table_dir, iterations),
             "project": lambda: parquet_scan(name, table_dir, iterations, columns),
             "meta": lambda: parquet_meta(name, table_dir, iterations)}
    print(json.dumps(steps[action]()))


if __name__ == "__main__":
    main(sys.argv[1:])
