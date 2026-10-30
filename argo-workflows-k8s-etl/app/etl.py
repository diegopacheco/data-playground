import argparse
import json
import sys
from pathlib import Path
import data


def write(path, text):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(text)


def read_lines(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line]


def extract(seed, rows, out):
    batch = data.orders(seed, rows)
    write(f"{out}/orders.json", "".join(json.dumps(o, separators=(",", ":")) + "\n" for o in batch))
    write(f"{out}/regions.json", json.dumps(sorted({o["region"] for o in batch})))
    write(f"{out}/count", str(len(batch)))
    return batch


def summarize(region, rows, big_cents):
    mine = [o for o in rows if o["region"] == region]
    return {
        "region": region,
        "orders": len(mine),
        "cents": sum(o["cents"] for o in mine),
        "max_cents": max((o["cents"] for o in mine), default=0),
        "big_orders": sum(1 for o in mine if o["cents"] >= big_cents),
        "days": len({o["day"] for o in mine}),
    }


def transform(region, source, out, big_cents, fail_region, attempt):
    if region == fail_region and attempt == 0:
        print(f"transform {region} attempt {attempt} failing on purpose to exercise retryStrategy", flush=True)
        sys.exit(3)
    part = summarize(region, read_lines(source), big_cents)
    write(out, json.dumps(part))
    print(f"transform {region} attempt {attempt} ok {part}", flush=True)
    return part


def merge(parts, out):
    regions = sorted((json.loads(p.read_text()) for p in Path(parts).rglob("*.json")), key=lambda r: r["region"])
    report = {
        "regions": regions,
        "orders": sum(r["orders"] for r in regions),
        "cents": sum(r["cents"] for r in regions),
        "max_region_cents": max((r["cents"] for r in regions), default=0),
    }
    write(f"{out}/report.json", json.dumps(report))
    write(f"{out}/max_region_cents", str(report["max_region_cents"]))
    write(f"{out}/total_cents", str(report["cents"]))
    print(f"merged {len(regions)} parts, {report['orders']} orders, {report['cents']} cents", flush=True)
    return report


def load(source, batch, seed, rows):
    import warehouse
    report = json.loads(Path(source).read_text())
    warehouse.load(batch, seed, rows, report)
    print(f"loaded batch {batch} with {len(report['regions'])} region rows", flush=True)


def alert(source, batch, threshold):
    import warehouse
    report = json.loads(Path(source).read_text())
    hot = [r for r in report["regions"] if r["cents"] > threshold]
    warehouse.alert(batch, threshold, hot)
    print(f"alert batch {batch}: {[r['region'] for r in hot]} above {threshold}", flush=True)


def main(argv):
    p = argparse.ArgumentParser(prog="etl")
    sub = p.add_subparsers(dest="step", required=True)
    e = sub.add_parser("extract")
    e.add_argument("--seed", type=int, required=True)
    e.add_argument("--rows", type=int, required=True)
    e.add_argument("--out", required=True)
    t = sub.add_parser("transform")
    t.add_argument("--region", required=True)
    t.add_argument("--source", required=True)
    t.add_argument("--out", required=True)
    t.add_argument("--big-cents", type=int, required=True)
    t.add_argument("--fail-region", default="")
    t.add_argument("--attempt", type=int, default=0)
    m = sub.add_parser("merge")
    m.add_argument("--parts", required=True)
    m.add_argument("--out", required=True)
    lo = sub.add_parser("load")
    lo.add_argument("--source", required=True)
    lo.add_argument("--batch", required=True)
    lo.add_argument("--seed", type=int, required=True)
    lo.add_argument("--rows", type=int, required=True)
    a = sub.add_parser("alert")
    a.add_argument("--source", required=True)
    a.add_argument("--batch", required=True)
    a.add_argument("--threshold", type=int, required=True)
    args = p.parse_args(argv)
    if args.step == "extract":
        extract(args.seed, args.rows, args.out)
    elif args.step == "transform":
        transform(args.region, args.source, args.out, args.big_cents, args.fail_region, args.attempt)
    elif args.step == "merge":
        merge(args.parts, args.out)
    elif args.step == "load":
        load(args.source, args.batch, args.seed, args.rows)
    else:
        alert(args.source, args.batch, args.threshold)


if __name__ == "__main__":
    main(sys.argv[1:])
