import io
import statistics
import time
import urllib.request

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.csv as pacsv
import pyarrow.flight as fl

SCHEMA = pa.schema([
    ("order_id", pa.int64()),
    ("customer", pa.string()),
    ("product", pa.string()),
    ("category", pa.string()),
    ("quantity", pa.int32()),
    ("price", pa.float64()),
    ("ts", pa.string()),
])


def read_orders_csv(source):
    options = pacsv.ConvertOptions(column_types=SCHEMA, strings_can_be_null=False)
    return pacsv.read_csv(source, convert_options=options).select(SCHEMA.names)


def revenue_of(table):
    return round(pc.sum(pc.multiply(pc.cast(table["quantity"], pa.float64()), table["price"])).as_py(), 2)


class OrdersClient:
    def __init__(self, flight_url, csv_url):
        self.client = fl.connect(flight_url)
        self.csv_url = csv_url

    def flights(self):
        return [
            {
                "name": info.descriptor.path[0].decode(),
                "records": info.total_records,
                "bytes": info.total_bytes,
                "schema": [f"{f.name}: {f.type}" for f in info.schema],
            }
            for info in self.client.list_flights()
        ]

    def info(self, name):
        return self.client.get_flight_info(fl.FlightDescriptor.for_path(name))

    def fetch(self, ticket):
        return self.client.do_get(fl.Ticket(ticket)).read_all()

    def upload(self, table):
        writer, reader = self.client.do_put(fl.FlightDescriptor.for_path("orders"), SCHEMA)
        writer.write_table(table.cast(SCHEMA))
        writer.close()
        return table.num_rows

    def reset(self):
        return int(b"".join(r.body.to_pybytes() for r in self.client.do_action(fl.Action("reset", b""))))

    def fetch_bench_flight(self):
        start = time.perf_counter()
        table = self.fetch("bench")
        seconds = time.perf_counter() - start
        return table, {"seconds": seconds, "bytes": table.nbytes, "rows": table.num_rows}

    def fetch_bench_csv(self):
        start = time.perf_counter()
        with urllib.request.urlopen(self.csv_url) as response:
            body = response.read()
        downloaded = time.perf_counter()
        table = read_orders_csv(io.BytesIO(body))
        parsed = time.perf_counter()
        return table, body, {
            "seconds": parsed - start,
            "download_seconds": downloaded - start,
            "parse_seconds": parsed - downloaded,
            "bytes": len(body),
            "rows": table.num_rows,
        }

    def benchmark(self, rounds=3):
        flight_runs, csv_runs = [], []
        same = True
        for _ in range(rounds):
            flight_table, flight_stats = self.fetch_bench_flight()
            csv_table, _, csv_stats = self.fetch_bench_csv()
            same = same and flight_table.equals(csv_table)
            flight_runs.append(flight_stats)
            csv_runs.append(csv_stats)
        flight = summarize(flight_runs)
        csv = summarize(csv_runs)
        return {
            "rounds": rounds,
            "rows": flight["rows"],
            "identical": same,
            "revenue": revenue_of(flight_table),
            "flight": flight,
            "csv": csv,
            "speedup": round(csv["median_seconds"] / flight["median_seconds"], 2),
        }


def summarize(runs):
    medians = {k: statistics.median(r[k] for r in runs) for k in runs[0] if k.endswith("seconds")}
    return {
        "rows": runs[0]["rows"],
        "bytes": runs[0]["bytes"],
        "runs": [round(r["seconds"], 4) for r in runs],
        "median_seconds": round(medians["seconds"], 4),
        "median_download_seconds": round(medians.get("download_seconds", medians["seconds"]), 4),
        "median_parse_seconds": round(medians.get("parse_seconds", 0.0), 4),
        "rows_per_second": int(runs[0]["rows"] / medians["seconds"]),
        "mb_per_second": round(runs[0]["bytes"] / medians["seconds"] / 1_000_000, 1),
    }
