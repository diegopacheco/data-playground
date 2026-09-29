import sys

import settings
from flight_client import read_orders_csv


def show_revenue(title, table):
    print(title)
    for row in table.to_pylist():
        print(f"  {row['category']:<12} orders={row['orders']:<4} units={row['units']:<5} revenue={row['revenue']:.2f}")


def main(rounds):
    client = settings.client()
    print(f"reset -> {client.reset()} rows")
    for flight in client.flights():
        print(f"flight {flight['name']:<20} records={flight['records']:<8} bytes={flight['bytes']}")

    before = client.fetch("orders")
    print(f"orders before upload: {before.num_rows} rows")
    show_revenue("revenue_by_category before upload", client.fetch("revenue_by_category"))

    uploaded = client.upload(read_orders_csv(settings.NEW_ORDERS_CSV))
    print(f"do_put uploaded {uploaded} rows")

    after = client.fetch("orders")
    print(f"orders after upload: {after.num_rows} rows (+{after.num_rows - before.num_rows})")
    show_revenue("revenue_by_category after upload", client.fetch("revenue_by_category"))

    result = client.benchmark(rounds)
    print(f"benchmark rows={result['rows']} rounds={result['rounds']} identical={result['identical']} revenue={result['revenue']:.2f}")
    for name in ("flight", "csv"):
        r = result[name]
        print(f"  {name:<6} median={r['median_seconds']}s download={r['median_download_seconds']}s parse={r['median_parse_seconds']}s "
              f"bytes={r['bytes']} rows/s={r['rows_per_second']} MB/s={r['mb_per_second']} runs={r['runs']}")
    print(f"  flight speedup over csv+http: {result['speedup']}x")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 3)
