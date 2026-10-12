import json
import resource
import statistics
import sys
import time
from datetime import date
from engines import ENGINES


def rss_mb():
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return peak / 1e6 if sys.platform == "darwin" else peak / 1e3


def normalize(rows):
    return [[v.isoformat() if isinstance(v, date) else v for v in r] for r in rows]


def timed(run, q):
    t0 = time.perf_counter()
    rows = run(q)
    return (time.perf_counter() - t0) * 1000, rows


def main():
    engine, q, runs = sys.argv[1], sys.argv[2], int(sys.argv[3])
    run = ENGINES[engine]()
    base = rss_mb()
    cold, rows = timed(run, q)
    warm = [timed(run, q)[0] for _ in range(runs)]
    print(json.dumps({
        "cold_ms": round(cold, 2),
        "warm_ms": [round(w, 2) for w in warm],
        "warm_median_ms": round(statistics.median(warm), 2),
        "base_rss_mb": round(base, 1),
        "peak_rss_mb": round(rss_mb(), 1),
        "rows": normalize(rows),
    }))


if __name__ == "__main__":
    main()
