import json
from importlib import metadata
import os
import time
import numpy as np
import datasketches as ds

DATA = os.environ.get("DATA_DIR", "/data")
RESULTS = os.environ.get("RESULTS_DIR", "/app/results")
SKETCHES = os.path.join(RESULTS, "sketches")
PARTITIONS = 8
HLL_LG_K = 12
KLL_K = 200
THETA_LG_K = 12
FREQ_LG_MAX_K = 10
CM_BUCKETS = ds.count_min_sketch.suggest_num_buckets(0.001)
CM_HASHES = ds.count_min_sketch.suggest_num_hashes(0.99)
NUM_STD = 2
QUANTILES = [0.5, 0.95, 0.99]
HLL_SWEEP = [8, 9, 10, 11, 12, 13, 14, 15, 16]
KLL_SWEEP = [50, 100, 200, 400, 800]
THETA_SWEEP = [8, 10, 12, 14, 16]
TOP_ITEMS = 10


def load(p):
    with np.load(os.path.join(DATA, f"part-{p}.npz")) as z:
        return {k: z[k] for k in z.files}


def load_many(parts):
    rows = [load(p) for p in parts]
    return {k: np.concatenate([r[k] for r in rows]) for k in rows[0]}


def hll_of(values, lg_k=HLL_LG_K):
    sk = ds.hll_sketch(lg_k, ds.tgt_hll_type.HLL_4)
    for v in values.tolist():
        sk.update(v)
    return sk


def theta_of(values, lg_k=THETA_LG_K):
    sk = ds.update_theta_sketch(lg_k)
    for v in values.tolist():
        sk.update(v)
    return sk.compact()


def kll_of(values, k=KLL_K):
    sk = ds.kll_floats_sketch(k)
    sk.update(values)
    return sk


def freq_of(items):
    sk = ds.frequent_strings_sketch(FREQ_LG_MAX_K)
    ids, counts = np.unique(items, return_counts=True)
    for i, c in zip(ids.tolist(), counts.tolist()):
        sk.update(str(i), c)
    return sk


def cm_of(items):
    sk = ds.count_min_sketch(CM_HASHES, CM_BUCKETS)
    for v in items.tolist():
        sk.update(v)
    return sk


def partition_sketches(rows):
    return {
        "hll": hll_of(rows["user"]),
        "kll": kll_of(rows["latency"]),
        "theta_web": theta_of(rows["user"][rows["platform"] == 0]),
        "theta_mobile": theta_of(rows["user"][rows["platform"] == 1]),
        "freq": freq_of(rows["item"]),
        "cm": cm_of(rows["item"]),
    }


def serialize(kind, sk):
    return sk.serialize_compact() if kind == "hll" else sk.serialize()


def deserialize(kind, blob):
    if kind == "hll":
        return ds.hll_sketch.deserialize(blob)
    if kind == "kll":
        return ds.kll_floats_sketch.deserialize(blob)
    if kind.startswith("theta"):
        return ds.compact_theta_sketch.deserialize(blob)
    if kind == "freq":
        return ds.frequent_strings_sketch.deserialize(blob)
    return ds.count_min_sketch.deserialize(blob)


KINDS = ["hll", "kll", "theta_web", "theta_mobile", "freq", "cm"]


def save(p, sketches):
    os.makedirs(SKETCHES, exist_ok=True)
    for kind, sk in sketches.items():
        with open(os.path.join(SKETCHES, f"p{p}.{kind}.bin"), "wb") as f:
            f.write(serialize(kind, sk))


def read(p, kind):
    with open(os.path.join(SKETCHES, f"p{p}.{kind}.bin"), "rb") as f:
        return f.read()


def bounds(sk):
    return {"estimate": sk.get_estimate(), "lower": sk.get_lower_bound(NUM_STD), "upper": sk.get_upper_bound(NUM_STD)}


def merge(parts):
    started = time.perf_counter()
    blobs = {kind: [read(p, kind) for p in parts] for kind in KINDS}
    hll = ds.hll_union(HLL_LG_K)
    kll = ds.kll_floats_sketch(KLL_K)
    web = ds.theta_union(THETA_LG_K)
    mobile = ds.theta_union(THETA_LG_K)
    freq = ds.frequent_strings_sketch(FREQ_LG_MAX_K)
    cm = ds.count_min_sketch(CM_HASHES, CM_BUCKETS)
    for i in range(len(parts)):
        hll.update(deserialize("hll", blobs["hll"][i]))
        kll.merge(deserialize("kll", blobs["kll"][i]))
        web.update(deserialize("theta_web", blobs["theta_web"][i]))
        mobile.update(deserialize("theta_mobile", blobs["theta_mobile"][i]))
        freq.merge(deserialize("freq", blobs["freq"][i]))
        cm.merge(deserialize("cm", blobs["cm"][i]))
    hll_sk = hll.get_result(ds.tgt_hll_type.HLL_4)
    web_sk = web.get_result()
    mobile_sk = mobile.get_result()
    return {
        "partitions": list(parts),
        "input_bytes": sum(len(b) for bl in blobs.values() for b in bl),
        "hll": {**bounds(hll_sk), "bytes": hll_sk.get_compact_serialization_bytes(), "lg_k": HLL_LG_K},
        "kll": kll_summary(kll),
        "theta": theta_ops(web_sk, mobile_sk),
        "frequent": freq_summary(freq, cm),
        "merge_ms": round((time.perf_counter() - started) * 1000, 2),
    }


def kll_summary(kll):
    return {
        "k": kll.k,
        "n": kll.n,
        "retained": kll.num_retained,
        "bytes": len(kll.serialize()),
        "rank_error": ds.kll_floats_sketch.get_normalized_rank_error(kll.k, False),
        "quantiles": {str(q): float(kll.get_quantile(q)) for q in QUANTILES},
    }


def theta_ops(web, mobile):
    union = ds.theta_union(THETA_LG_K)
    union.update(web)
    union.update(mobile)
    inter = ds.theta_intersection()
    inter.update(web)
    inter.update(mobile)
    ops = {
        "web": web,
        "mobile": mobile,
        "union": union.get_result(),
        "intersection": inter.get_result(),
        "web_not_mobile": ds.theta_a_not_b().compute(web, mobile),
    }
    return {name: {**bounds(sk), "bytes": len(sk.serialize()), "retained": sk.num_retained} for name, sk in ops.items()}


def freq_summary(freq, cm):
    rows = freq.get_frequent_items(ds.frequent_items_error_type.NO_FALSE_NEGATIVES)
    top = sorted(rows, key=lambda r: -r[1])[:TOP_ITEMS]
    return {
        "total": freq.total_weight,
        "epsilon": freq.epsilon,
        "max_error": freq.epsilon * freq.total_weight,
        "reported": len(rows),
        "bytes": freq.get_serialized_size_bytes(),
        "cm_bytes": cm.get_serialized_size_bytes(),
        "cm_relative_error": cm.get_relative_error(),
        "cm_hashes": cm.num_hashes,
        "cm_buckets": cm.num_buckets,
        "items": [
            {
                "item": int(item),
                "estimate": est,
                "lower": lb,
                "upper": ub,
                "cm_estimate": cm.get_estimate(int(item)),
                "cm_upper": cm.get_upper_bound(int(item)),
            }
            for item, est, lb, ub in top
        ],
        "all_items": [int(r[0]) for r in rows],
    }


def exact(rows):
    users = np.unique(rows["user"])
    web = np.unique(rows["user"][rows["platform"] == 0])
    mobile = np.unique(rows["user"][rows["platform"] == 1])
    lat = np.sort(rows["latency"])
    n = lat.size
    items = np.bincount(rows["item"])
    nonzero = np.count_nonzero(items)
    sets = {
        "web": web.size,
        "mobile": mobile.size,
        "union": np.union1d(web, mobile).size,
        "intersection": np.intersect1d(web, mobile, assume_unique=True).size,
        "web_not_mobile": np.setdiff1d(web, mobile, assume_unique=True).size,
    }
    return {
        "rows": int(n),
        "distinct_users": int(users.size),
        "users_bytes": int(users.nbytes),
        "latency_bytes": int(lat.nbytes),
        "quantiles": {str(q): float(lat[min(n - 1, int(np.ceil(q * n)) - 1)]) for q in QUANTILES},
        "sets": {k: int(v) for k, v in sets.items()},
        "sets_bytes": int(web.nbytes + mobile.nbytes),
        "items_bytes": int(nonzero * 12),
        "distinct_items": int(nonzero),
    }, users, lat, items


def rank_of(sorted_values, v):
    lo = np.searchsorted(sorted_values, v, "left") / sorted_values.size
    hi = np.searchsorted(sorted_values, v, "right") / sorted_values.size
    return float(lo), float(hi)


def hll_sweep(users, exact_count):
    out = []
    for lg_k in HLL_SWEEP:
        sk = hll_of(users, lg_k)
        est = sk.get_estimate()
        out.append({
            "lg_k": lg_k,
            "estimate": est,
            "lower": sk.get_lower_bound(NUM_STD),
            "upper": sk.get_upper_bound(NUM_STD),
            "error": (est - exact_count) / exact_count,
            "bound": abs(ds.hll_sketch.get_rel_err(True, False, lg_k, NUM_STD)),
            "bytes": sk.get_compact_serialization_bytes(),
        })
    return out


def kll_sweep(latency, sorted_lat):
    out = []
    for k in KLL_SWEEP:
        sk = kll_of(latency, k)
        worst = 0.0
        for q in QUANTILES:
            lo, hi = rank_of(sorted_lat, sk.get_quantile(q))
            worst = max(worst, 0.0 if lo <= q <= hi else min(abs(q - lo), abs(q - hi)))
        out.append({
            "k": k,
            "bound": ds.kll_floats_sketch.get_normalized_rank_error(k, False),
            "worst_rank_error": worst,
            "bytes": len(sk.serialize()),
            "retained": sk.num_retained,
        })
    return out


def theta_sweep(rows, exact_sets):
    web_users = rows["user"][rows["platform"] == 0]
    mobile_users = rows["user"][rows["platform"] == 1]
    out = []
    for lg_k in THETA_SWEEP:
        web = theta_of(web_users, lg_k)
        mobile = theta_of(mobile_users, lg_k)
        inter = ds.theta_intersection()
        inter.update(web)
        inter.update(mobile)
        sk = inter.get_result()
        est = sk.get_estimate()
        truth = exact_sets["intersection"]
        out.append({
            "lg_k": lg_k,
            "estimate": est,
            "lower": sk.get_lower_bound(NUM_STD),
            "upper": sk.get_upper_bound(NUM_STD),
            "error": (est - truth) / truth,
            "bytes": len(web.serialize()) + len(mobile.serialize()),
        })
    return out


def run():
    started = time.perf_counter()
    parts = list(range(PARTITIONS))
    per_partition = []
    build_ms = 0.0
    for p in parts:
        rows = load(p)
        t = time.perf_counter()
        sketches = partition_sketches(rows)
        build_ms += (time.perf_counter() - t) * 1000
        save(p, sketches)
        per_partition.append({
            "partition": p,
            "rows": int(rows["user"].size),
            "hll_estimate": sketches["hll"].get_estimate(),
            "hll_lower": sketches["hll"].get_lower_bound(NUM_STD),
            "hll_upper": sketches["hll"].get_upper_bound(NUM_STD),
            "exact_distinct": int(np.unique(rows["user"]).size),
            "bytes": sum(len(serialize(k, s)) for k, s in sketches.items()),
        })
        print(f"partition {p}: sketched {rows['user'].size} rows")
    merged = merge(parts)
    rows = load_many(parts)
    truth, users, sorted_lat, item_counts = exact(rows)
    for row in merged["frequent"]["items"]:
        row["exact"] = int(item_counts[row["item"]])
    for q in QUANTILES:
        lo, hi = rank_of(sorted_lat, merged["kll"]["quantiles"][str(q)])
        merged["kll"].setdefault("ranks", {})[str(q)] = {"lower": lo, "upper": hi}
    t = time.perf_counter()
    single = hll_of(rows["user"])
    single_ms = (time.perf_counter() - t) * 1000
    result = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "datasketches": metadata.version("datasketches"),
        "numpy": np.__version__,
        "num_std": NUM_STD,
        "config": {
            "hll_lg_k": HLL_LG_K,
            "hll_type": "HLL_4",
            "kll_k": KLL_K,
            "theta_lg_k": THETA_LG_K,
            "freq_lg_max_k": FREQ_LG_MAX_K,
            "cm_hashes": CM_HASHES,
            "cm_buckets": CM_BUCKETS,
        },
        "partitions": per_partition,
        "merged": merged,
        "exact": truth,
        "single_pass_hll": {**bounds(single), "ms": round(single_ms, 1)},
        "hll_sweep": hll_sweep(users, truth["distinct_users"]),
        "kll_sweep": kll_sweep(rows["latency"], sorted_lat),
        "theta_sweep": theta_sweep(rows, truth["sets"]),
        "build_ms": round(build_ms, 1),
        "total_ms": round((time.perf_counter() - started) * 1000, 1),
    }
    os.makedirs(RESULTS, exist_ok=True)
    with open(os.path.join(RESULTS, "results.json"), "w") as f:
        json.dump(result, f, indent=1)
    print(f"distinct users exact={truth['distinct_users']} hll={merged['hll']['estimate']:.0f}")
    print(f"wrote results.json in {result['total_ms']:.0f} ms")
    return result


if __name__ == "__main__":
    run()
