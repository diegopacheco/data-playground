import h3
from data import POINTS


def city_points(city):
    return [p for p in POINTS if p["city"] == city]


def cell_of(p, res):
    return h3.latlng_to_cell(p["lat"], p["lng"], res)


def cell_stats(city, res):
    stats = {}
    for p in city_points(city):
        s = stats.setdefault(cell_of(p, res), {"n": 0, "fare_sum": 0, "wait_sum": 0})
        s["n"] += 1
        s["fare_sum"] += p["fare_cents"]
        s["wait_sum"] += p["wait_s"]
    return {
        cell: {"n": s["n"], "fare_sum": s["fare_sum"], "avg_fare": s["fare_sum"] / s["n"], "avg_wait": s["wait_sum"] / s["n"]}
        for cell, s in stats.items()
    }


def rollup(city, child_res, parent_res):
    parents = {}
    for cell, s in cell_stats(city, child_res).items():
        agg = parents.setdefault(h3.cell_to_parent(cell, parent_res), {"n": 0, "fare_sum": 0})
        agg["n"] += s["n"]
        agg["fare_sum"] += s["fare_sum"]
    return parents


def smoothed(city, res, k):
    counts = {cell: s["n"] for cell, s in cell_stats(city, res).items()}
    targets = {t for cell in counts for t in h3.grid_disk(cell, k)}
    return {t: sum(counts.get(c, 0) for c in h3.grid_disk(t, k)) / (1 + 3 * k * (k + 1)) for t in targets}


def polyfill(polygon, res):
    return set(h3.polygon_to_cells(h3.LatLngPoly(polygon), res))


def region_points(city, polygon, res):
    cells = polyfill(polygon, res)
    return {p["id"] for p in city_points(city) if cell_of(p, res) in cells}


def parent_mismatches(city, child_res, parent_res):
    return sum(1 for p in city_points(city) if h3.cell_to_parent(cell_of(p, child_res), parent_res) != cell_of(p, parent_res))


def boundary(cell):
    return [[round(lat, 6), round(lng, 6)] for lat, lng in h3.cell_to_boundary(cell)]
