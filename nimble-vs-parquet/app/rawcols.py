import os

import numpy as np
import pyarrow as pa

KINDS = {pa.int64(): "bigint", pa.float64(): "double", pa.string(): "varchar"}
ARROW = {"bigint": pa.int64(), "double": pa.float64(), "varchar": pa.string()}


def string_parts(array):
    array = array.cast(pa.large_string())
    _, offsets, data = array.buffers()
    offsets = np.frombuffer(offsets, dtype=np.int64)[array.offset:array.offset + len(array) + 1]
    data = np.frombuffer(data, dtype=np.uint8) if data is not None else np.zeros(0, dtype=np.uint8)
    data = data[offsets[0]:offsets[-1]]
    return offsets - offsets[0], data


def write_dir(table, path):
    os.makedirs(path, exist_ok=True)
    lines = [f"rows {table.num_rows}"]
    for i, field in enumerate(table.schema):
        kind = KINDS[field.type]
        lines.append(f"{field.name} {kind}")
        column = table.column(i).combine_chunks()
        base = os.path.join(path, f"c{i}")
        if kind == "varchar":
            offsets, data = string_parts(column)
            offsets.astype("<i8").tofile(base + ".off")
            data.tofile(base + ".bin")
        else:
            column.to_numpy(zero_copy_only=True).astype("<" + ("i8" if kind == "bigint" else "f8")).tofile(base + ".bin")
    with open(os.path.join(path, "schema.txt"), "w") as f:
        f.write("\n".join(lines) + "\n")


def read_schema(path):
    with open(os.path.join(path, "schema.txt")) as f:
        lines = f.read().split("\n")
    rows = int(lines[0].split()[1])
    columns = [tuple(line.split()) for line in lines[1:] if line.strip()]
    return rows, columns


def read_dir(path, names=None):
    rows, columns = read_schema(path)
    arrays = []
    for i, (name, kind) in enumerate(columns):
        if names is not None and name not in names:
            continue
        base = os.path.join(path, f"c{i}")
        if kind == "varchar":
            offsets = np.fromfile(base + ".off", dtype="<i8")
            data = np.fromfile(base + ".bin", dtype=np.uint8)
            arrays.append(pa.LargeStringArray.from_buffers(rows, pa.py_buffer(offsets), pa.py_buffer(data)).cast(pa.string()))
        else:
            arrays.append(pa.array(np.fromfile(base + ".bin", dtype="<i8" if kind == "bigint" else "<f8")))
    return pa.table(arrays, names=[name for name, _ in columns if names is None or name in names])


def same_bytes(left, right):
    left_rows, left_columns = read_schema(left)
    right_rows, right_columns = read_schema(right)
    if left_rows != right_rows or left_columns != right_columns:
        return False
    for name in sorted(os.listdir(left)):
        if name == "schema.txt":
            continue
        with open(os.path.join(left, name), "rb") as a, open(os.path.join(right, name), "rb") as b:
            if a.read() != b.read():
                return False
    return True
