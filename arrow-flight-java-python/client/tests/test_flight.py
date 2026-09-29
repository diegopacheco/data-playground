import subprocess
import sys
from pathlib import Path

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.flight as fl
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import settings
from flight_client import read_orders_csv, revenue_of

AWK_REVENUE = 'FNR>1{o[$4]++; u[$4]+=$5; r[$4]+=$5*$6} END{for(c in o) printf "%s,%d,%d,%.2f\\n", c, o[c], u[c], r[c]}'
AWK_TOTALS = 'NR>1{n++; r+=$5*$6; m=$1} END{printf "%d,%.2f,%d\\n", n, r, m}'


def awk(program, *files):
    out = subprocess.run(["awk", "-F,", program, *map(str, files)], check=True, capture_output=True, text=True).stdout
    return out.strip().splitlines()


def awk_revenue(*files):
    rows = {}
    for line in awk(AWK_REVENUE, *files):
        category, orders, units, revenue = line.split(",")
        rows[category] = (int(orders), int(units), float(revenue))
    return rows


def flight_revenue(client):
    return {r["category"]: (r["orders"], r["units"], r["revenue"]) for r in client.fetch("revenue_by_category").to_pylist()}


@pytest.fixture
def client():
    c = settings.client()
    c.reset()
    yield c
    c.reset()


def test_orders_stream_is_the_csv_loaded_into_arrow(client):
    fetched = client.fetch("orders").sort_by("order_id")
    expected = read_orders_csv(settings.ORDERS_CSV).sort_by("order_id")
    assert fetched.num_rows == 200
    assert fetched.equals(expected)


def test_server_side_revenue_matches_awk(client):
    assert flight_revenue(client) == awk_revenue(settings.ORDERS_CSV)


def test_do_put_changes_orders_and_revenue_exactly_by_the_uploaded_batch(client):
    before = flight_revenue(client)
    uploaded = client.upload(read_orders_csv(settings.NEW_ORDERS_CSV))
    after = flight_revenue(client)
    assert uploaded == 5
    assert client.fetch("orders").num_rows == 205
    assert client.info("orders").total_records == 205
    assert after == awk_revenue(settings.ORDERS_CSV, settings.NEW_ORDERS_CSV)
    assert "games" in after and "games" not in before
    assert after["books"][0] == before["books"][0] + 1


def test_do_put_with_wrong_schema_is_rejected(client):
    bad = pa.table({"order_id": pa.array([1], pa.int64())})
    writer, _ = client.client.do_put(fl.FlightDescriptor.for_path("orders"), bad.schema)
    writer.write_table(bad)
    with pytest.raises(pa.ArrowInvalid, match="schema must be"):
        writer.close()
    assert client.fetch("orders").num_rows == 200


def test_bench_flight_and_csv_carry_identical_million_rows_checked_by_awk(client, tmp_path):
    flight_table, stats = client.fetch_bench_flight()
    csv_table, body, _ = client.fetch_bench_csv()
    csv_file = tmp_path / "bench.csv"
    csv_file.write_bytes(body)
    rows, revenue, max_id = awk(AWK_TOTALS, csv_file)[0].split(",")
    assert stats["rows"] == client.info("bench").total_records == int(rows) == 1_000_000
    assert flight_table.equals(csv_table)
    assert revenue_of(flight_table) == float(revenue)
    assert pc.max(flight_table["order_id"]).as_py() == int(max_id) == 1_000_000
