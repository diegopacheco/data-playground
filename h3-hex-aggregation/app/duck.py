import threading
import duckdb
from data import GRID_STEP, POINTS

LOCK = threading.Lock()


def connect():
    con = duckdb.connect()
    con.execute("LOAD h3")
    con.execute("CREATE TABLE points (id VARCHAR, city VARCHAR, lat DOUBLE, lng DOUBLE, fare_cents BIGINT, wait_s BIGINT)")
    con.executemany(
        "INSERT INTO points VALUES (?, ?, ?, ?, ?, ?)",
        [(p["id"], p["city"], p["lat"], p["lng"], p["fare_cents"], p["wait_s"]) for p in POINTS],
    )
    return con


CON = connect()


def rows(sql, params=()):
    with LOCK:
        return CON.execute(sql, params).fetchall()


def version():
    return rows("SELECT version(), h3_version()")[0]


def cell_stats(city, res):
    return {
        cell: {"n": n, "fare_sum": fare_sum, "avg_fare": avg_fare, "avg_wait": avg_wait}
        for cell, n, fare_sum, avg_fare, avg_wait in rows(
            """SELECT h3_h3_to_string(h3_latlng_to_cell(lat, lng, $res)) AS cell, count(*), sum(fare_cents), avg(fare_cents), avg(wait_s)
               FROM points WHERE city = $city GROUP BY cell""",
            {"city": city, "res": res},
        )
    }


def rollup(city, child_res, parent_res):
    return {
        cell: {"n": n, "fare_sum": fare_sum}
        for cell, n, fare_sum in rows(
            """WITH children AS (
                 SELECT h3_latlng_to_cell(lat, lng, $child) AS cell, count(*) AS n, sum(fare_cents) AS fare_sum
                 FROM points WHERE city = $city GROUP BY cell)
               SELECT h3_h3_to_string(h3_cell_to_parent(cell, $parent)) AS parent, sum(n)::BIGINT, sum(fare_sum)::BIGINT
               FROM children GROUP BY parent""",
            {"city": city, "child": child_res, "parent": parent_res},
        )
    }


def smoothed(city, res, k):
    size = 1 + 3 * k * (k + 1)
    return {
        cell: total / size
        for cell, total in rows(
            """WITH counts AS (
                 SELECT h3_latlng_to_cell(lat, lng, $res) AS cell, count(*) AS n
                 FROM points WHERE city = $city GROUP BY cell),
               spread AS (SELECT unnest(h3_grid_disk(cell, $k)) AS target, n FROM counts)
               SELECT h3_h3_to_string(target), sum(n) FROM spread GROUP BY target""",
            {"city": city, "res": res, "k": k},
        )
    }


def polygon_wkt(polygon):
    ring = polygon + [polygon[0]]
    return "POLYGON((" + ", ".join(f"{lng} {lat}" for lat, lng in ring) + "))"


def polyfill(polygon, res):
    return {
        cell
        for (cell,) in rows(
            "SELECT h3_h3_to_string(unnest(h3_polygon_wkt_to_cells($wkt, $res)))",
            {"wkt": polygon_wkt(polygon), "res": res},
        )
    }


def region_points(city, polygon, res):
    return {
        pid
        for (pid,) in rows(
            """SELECT id FROM points
               WHERE city = $city AND list_contains(h3_polygon_wkt_to_cells($wkt, $res), h3_latlng_to_cell(lat, lng, $res))""",
            {"city": city, "wkt": polygon_wkt(polygon), "res": res},
        )
    }


def parent_mismatches(city, child_res, parent_res):
    return rows(
        """SELECT count(*) FROM points
           WHERE city = $city AND h3_cell_to_parent(h3_latlng_to_cell(lat, lng, $child), $parent) <> h3_latlng_to_cell(lat, lng, $parent)""",
        {"city": city, "child": child_res, "parent": parent_res},
    )[0][0]


def grid_stats(city):
    return {
        (int(row), int(col)): {"n": n, "avg_fare": avg_fare}
        for row, col, n, avg_fare in rows(
            """SELECT floor(lat / $step) AS r, floor(lng / $step) AS c, count(*), avg(fare_cents)
               FROM points WHERE city = $city GROUP BY r, c""",
            {"city": city, "step": GRID_STEP},
        )
    }
