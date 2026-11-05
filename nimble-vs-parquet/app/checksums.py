import numpy as np
import pyarrow as pa

from rawcols import string_parts

C1 = np.uint64(0x9E3779B97F4A7C15)
C2 = np.uint64(0xBF58476D1CE4E5B9)
C3 = np.uint64(0x94D049BB133111EB)


def splitmix(x):
    with np.errstate(over="ignore"):
        x = x + C1
        x = (x ^ (x >> np.uint64(30))) * C2
        x = (x ^ (x >> np.uint64(27))) * C3
        return x ^ (x >> np.uint64(31))


def string_hashes(offsets, data):
    lengths = np.diff(offsets)
    starts = np.repeat(offsets[:-1], lengths)
    positions = (np.arange(len(data), dtype=np.int64) - starts).astype(np.uint64)
    terms = splitmix((data.astype(np.uint64) << np.uint64(32)) | positions)
    with np.errstate(over="ignore"):
        running = np.concatenate([np.zeros(1, dtype=np.uint64), np.cumsum(terms, dtype=np.uint64)])
        return running[offsets[1:]] - running[offsets[:-1]] + splitmix(lengths.astype(np.uint64))


def column_bits(column):
    column = column.combine_chunks() if isinstance(column, pa.ChunkedArray) else column
    if column.null_count:
        raise ValueError("unexpected null")
    if pa.types.is_string(column.type) or pa.types.is_large_string(column.type):
        return string_hashes(*string_parts(column))
    return np.ascontiguousarray(column.to_numpy(zero_copy_only=False)).view(np.uint64)


def column_checksum(column):
    bits = column_bits(column)
    with np.errstate(over="ignore"):
        return int(np.sum(splitmix(bits + np.arange(len(bits), dtype=np.uint64)), dtype=np.uint64))


def table_checksums(table, names=None):
    return {name: str(column_checksum(table.column(name))) for name in (names or table.column_names)}
