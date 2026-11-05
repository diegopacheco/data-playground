import numpy as np
import pyarrow as pa

LABELS = np.array(["none", "low", "mid", "high", "spam", "ham", "new", "churned"])
CATEGORIES = np.array(["books", "electronics", "games", "garden", "home", "music", "sports", "toys", "tools", "beauty"])
COUNTRIES = np.array(["BR", "US", "DE", "FR", "IN", "JP", "MX", "CA", "AR", "PT", "ES", "IT", "NL", "SE", "PL", "KR", "AU", "CL", "CO", "ZA"])
PRODUCTS = np.array([f"product-{i:03d}" for i in range(200)])


def wide_kind(index):
    if index % 20 == 19:
        return "varchar"
    if index % 4 == 3:
        return "bigint"
    return "double"


def wide_column(rng, index, rows):
    kind = wide_kind(index)
    if kind == "varchar":
        return pa.array(LABELS[rng.integers(0, len(LABELS), rows)])
    if kind == "bigint":
        counts = rng.poisson(0.5 + index % 7, rows).astype(np.int64)
        counts[rng.random(rows) < 0.6] = 0
        return pa.array(counts)
    values = np.round(rng.normal(index % 13, 1 + index % 5, rows), 2)
    values[rng.random(rows) < 0.7] = 0.0
    return pa.array(values)


def wide_table(rows, columns, seed=42):
    rng = np.random.default_rng(seed)
    arrays = [pa.array(np.arange(1, rows + 1, dtype=np.int64))]
    names = ["row_id"]
    for i in range(columns - 1):
        arrays.append(wide_column(rng, i, rows))
        names.append(f"f{i:05d}")
    return pa.table(arrays, names=names)


def normal_table(rows, seed=7):
    rng = np.random.default_rng(seed)
    order_id = np.arange(1, rows + 1, dtype=np.int64)
    return pa.table({
        "order_id": order_id,
        "user_id": rng.integers(1, 100_001, rows, dtype=np.int64),
        "product": pa.array(PRODUCTS[rng.integers(0, len(PRODUCTS), rows)]),
        "category": pa.array(CATEGORIES[rng.integers(0, len(CATEGORIES), rows)]),
        "country": pa.array(COUNTRIES[rng.integers(0, len(COUNTRIES), rows)]),
        "quantity": rng.integers(1, 11, rows, dtype=np.int64),
        "price": np.round(rng.uniform(1, 500, rows), 2),
        "ts": 1_767_225_600_000 + order_id * 997 + rng.integers(0, 997, rows, dtype=np.int64),
    })


def projection(table, count):
    names = table.column_names
    if count >= len(names):
        return list(names)
    step = len(names) // count
    return [names[min(i * step + i, len(names) - 1)] for i in range(count)]
