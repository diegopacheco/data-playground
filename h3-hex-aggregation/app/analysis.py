import time
from functools import cache
import h3
import duck
import geo
import hexpy
from data import CITIES, GRID_STEP, POINTS, POINTS_PER_CITY, RESOLUTIONS, SEED

ROLLUP_CHILD = 9
ROLLUP_PARENT = 7
NEIGHBOUR_RES = 8
COMPARE_RES = 8


def busiest(stats):
    return max(stats, key=lambda c: (stats[c]["n"], c))


def summary():
    duckdb_version, h3_version = duck.version()
    return {
        "seed": SEED,
        "points": len(POINTS),
        "points_per_city": POINTS_PER_CITY,
        "resolutions": RESOLUTIONS,
        "grid_step": GRID_STEP,
        "duckdb": duckdb_version,
        "h3_extension": h3_version,
        "h3_py": h3.versions(),
        "cities": {k: {"name": c["name"], "box": c["box"], "region": c["region"]} for k, c in CITIES.items()},
        "average_hexagon_km2": {r: h3.average_hexagon_area(r, "km^2") for r in RESOLUTIONS},
    }


@cache
def hexmap(city, res):
    stats = duck.cell_stats(city, res)
    smooth = duck.smoothed(city, res, 1)
    cells = []
    for cell in sorted(set(stats) | set(smooth)):
        s = stats.get(cell)
        cells.append({
            "cell": cell,
            "n": s["n"] if s else 0,
            "avg_fare": s["avg_fare"] if s else None,
            "avg_wait": s["avg_wait"] if s else None,
            "smooth": smooth.get(cell, 0),
            "boundary": hexpy.boundary(cell),
        })
    return {
        "city": city,
        "res": res,
        "cells": cells,
        "nonempty": len(stats),
        "total": sum(s["n"] for s in stats.values()),
        "max_n": max(s["n"] for s in stats.values()),
        "max_smooth": max(smooth.values()),
        "avg_cell_km2": h3.average_hexagon_area(res, "km^2"),
    }


@cache
def rollup(city):
    children_stats = duck.cell_stats(city, ROLLUP_CHILD)
    rolled = duck.rollup(city, ROLLUP_CHILD, ROLLUP_PARENT)
    direct = duck.cell_stats(city, ROLLUP_PARENT)
    parent = max(rolled, key=lambda c: (rolled[c]["n"], c))
    children = []
    for cell in sorted(h3.cell_to_children(parent, ROLLUP_CHILD)):
        s = children_stats.get(cell, {"n": 0, "fare_sum": 0})
        children.append({"cell": cell, "n": s["n"], "fare_sum": s["fare_sum"], "mid": h3.cell_to_parent(cell, ROLLUP_CHILD - 1), "boundary": hexpy.boundary(cell)})
    mids = [{"cell": m, "n": sum(c["n"] for c in children if c["mid"] == m), "boundary": hexpy.boundary(m)} for m in sorted(h3.cell_to_children(parent, ROLLUP_CHILD - 1))]
    levels = []
    for res in range(ROLLUP_CHILD, min(RESOLUTIONS) - 1, -1):
        up = duck.rollup(city, ROLLUP_CHILD, res)
        straight = duck.cell_stats(city, res)
        levels.append({
            "res": res,
            "rollup_cells": len(up),
            "rollup_total": sum(s["n"] for s in up.values()),
            "rollup_fare_sum": sum(s["fare_sum"] for s in up.values()),
            "direct_cells": len(straight),
            "direct_total": sum(s["n"] for s in straight.values()),
            "mismatched_points": duck.parent_mismatches(city, ROLLUP_CHILD, res),
        })
    return {
        "city": city,
        "parent": parent,
        "parent_res": ROLLUP_PARENT,
        "child_res": ROLLUP_CHILD,
        "parent_boundary": hexpy.boundary(parent),
        "rollup": rolled[parent],
        "rollup_avg_fare": rolled[parent]["fare_sum"] / rolled[parent]["n"],
        "direct": direct.get(parent, {"n": 0, "fare_sum": 0}),
        "children": children,
        "mids": mids,
        "levels": levels,
    }


def grid_neighbour_km(lat, lng):
    row, col = int(lat // GRID_STEP), int(lng // GRID_STEP)
    center = ((row + 0.5) * GRID_STEP, (col + 0.5) * GRID_STEP)
    out = []
    for dr in (-1, 0, 1):
        for dc in (-1, 0, 1):
            if dr or dc:
                out.append(geo.haversine_km(center, ((row + dr + 0.5) * GRID_STEP, (col + dc + 0.5) * GRID_STEP)))
    return out


@cache
def neighbours(city):
    stats = duck.cell_stats(city, NEIGHBOUR_RES)
    center = busiest(stats)
    smooth = duck.smoothed(city, NEIGHBOUR_RES, 1)
    smooth2 = duck.smoothed(city, NEIGHBOUR_RES, 2)
    clat, clng = h3.cell_to_latlng(center)
    cells = []
    for cell in sorted(h3.grid_disk(center, 2)):
        cells.append({
            "cell": cell,
            "ring": h3.grid_distance(center, cell),
            "n": stats.get(cell, {"n": 0})["n"],
            "km_from_center": geo.haversine_km((clat, clng), h3.cell_to_latlng(cell)),
            "boundary": hexpy.boundary(cell),
        })
    ring1 = [c["km_from_center"] for c in cells if c["ring"] == 1]
    grid = grid_neighbour_km(clat, clng)
    return {
        "city": city,
        "res": NEIGHBOUR_RES,
        "center": center,
        "cells": cells,
        "center_n": stats[center]["n"],
        "smooth_k1": smooth[center],
        "smooth_k2": smooth2[center],
        "hex_neighbour_km": geo.spread(ring1),
        "grid_neighbour_km": geo.spread(grid),
    }


@cache
def region(city, res):
    polygon = CITIES[city]["region"]
    cells = duck.polyfill(polygon, res)
    by_hex = duck.region_points(city, polygon, res)
    lats = [p[0] for p in polygon]
    lngs = [p[1] for p in polygon]
    pad = 0.006
    points = []
    exact = set()
    for p in hexpy.city_points(city):
        is_exact = geo.inside(p["lat"], p["lng"], polygon)
        if is_exact:
            exact.add(p["id"])
        if min(lats) - pad <= p["lat"] <= max(lats) + pad and min(lngs) - pad <= p["lng"] <= max(lngs) + pad:
            points.append({"lat": p["lat"], "lng": p["lng"], "exact": is_exact, "hex": p["id"] in by_hex})
    return {
        "city": city,
        "res": res,
        "polygon": polygon,
        "cells": [{"cell": c, "boundary": hexpy.boundary(c)} for c in sorted(cells)],
        "points": points,
        "exact": len(exact),
        "hex": len(by_hex),
        "both": len(exact & by_hex),
        "only_exact": len(exact - by_hex),
        "only_hex": len(by_hex - exact),
        "polygon_km2_by_cells": sum(h3.cell_area(c, "km^2") for c in cells),
    }


@cache
def compare(city):
    grid = duck.grid_stats(city)
    hexes = duck.cell_stats(city, COMPARE_RES)
    grid_cells = []
    for (row, col), s in sorted(grid.items()):
        south, west = row * GRID_STEP, col * GRID_STEP
        grid_cells.append({"row": row, "col": col, "n": s["n"], "rect": [south, west, south + GRID_STEP, west + GRID_STEP], "km2": geo.rect_area_km2(south, west, south + GRID_STEP, west + GRID_STEP)})
    hex_cells = [{"cell": c, "n": s["n"], "km2": h3.cell_area(c, "km^2"), "boundary": hexpy.boundary(c)} for c, s in sorted(hexes.items())]
    nb = neighbours(city)
    return {
        "city": city,
        "res": COMPARE_RES,
        "grid_step": GRID_STEP,
        "grid": grid_cells,
        "hex": hex_cells,
        "grid_nonempty": len(grid_cells),
        "hex_nonempty": len(hex_cells),
        "grid_max_n": max(c["n"] for c in grid_cells),
        "hex_max_n": max(c["n"] for c in hex_cells),
        "grid_km2": geo.spread([c["km2"] for c in grid_cells]),
        "hex_km2": geo.spread([c["km2"] for c in hex_cells]),
        "grid_neighbour_km": nb["grid_neighbour_km"],
        "hex_neighbour_km": nb["hex_neighbour_km"],
    }


def compare_all():
    return {city: {k: v for k, v in compare(city).items() if k not in ("grid", "hex")} for city in CITIES}


def timed(fn, *args):
    start = time.perf_counter()
    value = fn(*args)
    return value, round((time.perf_counter() - start) * 1000, 2)


def check(rows, city, name, res, py, dd, py_ms, dd_ms, size):
    rows.append({"city": city, "check": name, "res": res, "equal": py == dd, "size": size, "python_ms": py_ms, "duckdb_ms": dd_ms})


def same_stats(stats):
    return {c: (s["n"], s["fare_sum"], round(s["avg_fare"], 6), round(s["avg_wait"], 6)) for c, s in stats.items()}


def rounded(values):
    return {c: round(v, 9) for c, v in values.items()}


@cache
def crosscheck():
    rows = []
    for city, c in CITIES.items():
        for res in RESOLUTIONS:
            (py, py_ms), (dd, dd_ms) = timed(hexpy.cell_stats, city, res), timed(duck.cell_stats, city, res)
            check(rows, city, "cell counts, fare sum, averages", res, same_stats(py), same_stats(dd), py_ms, dd_ms, len(dd))
        for res in RESOLUTIONS[:-1]:
            (py, py_ms), (dd, dd_ms) = timed(hexpy.rollup, city, 9, res), timed(duck.rollup, city, 9, res)
            check(rows, city, "rollup res 9 to parent", res, py, dd, py_ms, dd_ms, len(dd))
            (py, py_ms), (dd, dd_ms) = timed(hexpy.parent_mismatches, city, 9, res), timed(duck.parent_mismatches, city, 9, res)
            check(rows, city, "points whose res 9 parent differs from direct cell", res, py, dd, py_ms, dd_ms, dd)
        for k in (1, 2):
            (py, py_ms), (dd, dd_ms) = timed(hexpy.smoothed, city, 8, k), timed(duck.smoothed, city, 8, k)
            check(rows, city, f"k-ring smoothing k={k}", 8, rounded(py), rounded(dd), py_ms, dd_ms, len(dd))
        for res in (8, 9):
            (py, py_ms), (dd, dd_ms) = timed(hexpy.polyfill, c["region"], res), timed(duck.polyfill, c["region"], res)
            check(rows, city, "polyfill cells", res, py, dd, py_ms, dd_ms, len(dd))
            (py, py_ms), (dd, dd_ms) = timed(hexpy.region_points, city, c["region"], res), timed(duck.region_points, city, c["region"], res)
            check(rows, city, "points in region by cell", res, py, dd, py_ms, dd_ms, len(dd))
    return {"checks": rows, "all_equal": all(r["equal"] for r in rows)}
