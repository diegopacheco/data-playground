from druid import sql

ROLLUP = "orders_rollup"
RAW = "orders_raw"

SEGMENTS_QUERY = f"""
SELECT datasource, "start", num_rows, "size"
FROM sys.segments
WHERE datasource IN ('{ROLLUP}', '{RAW}') AND is_published = 1 AND is_overshadowed = 0
ORDER BY "start"
"""

CATEGORY_QUERIES = {
    ROLLUP: f'SELECT category, SUM("count") AS orders, SUM(quantity) AS quantity, SUM(revenue) AS revenue FROM {ROLLUP} GROUP BY category ORDER BY category',
    RAW: f"SELECT category, COUNT(*) AS orders, SUM(quantity) AS quantity, SUM(revenue) AS revenue FROM {RAW} GROUP BY category ORDER BY category",
}

EVENT_QUERIES = {
    ROLLUP: f'SELECT COUNT(*) AS stored_rows, SUM("count") AS events FROM {ROLLUP}',
    RAW: f"SELECT COUNT(*) AS stored_rows, COUNT(*) AS events FROM {RAW}",
}


def summary():
    segments = sql(SEGMENTS_QUERY)
    result = {}
    for datasource, query in EVENT_QUERIES.items():
        counts = sql(query)[0]
        own = [s for s in segments if s["datasource"] == datasource]
        result[datasource] = {
            "events": counts["events"],
            "stored_rows": counts["stored_rows"],
            "segments": len(own),
            "bytes": sum(s["size"] for s in own),
        }
    rollup = result[ROLLUP]
    result["rollup_ratio"] = round(rollup["events"] / rollup["stored_rows"], 4)
    result["rows_saved"] = result[RAW]["stored_rows"] - rollup["stored_rows"]
    return result


def segments_per_day():
    days = {}
    for s in sql(SEGMENTS_QUERY):
        day = days.setdefault(s["start"][:10], {"day": s["start"][:10]})
        prefix = "rollup" if s["datasource"] == ROLLUP else "raw"
        day[f"{prefix}_segments"] = day.get(f"{prefix}_segments", 0) + 1
        day[f"{prefix}_rows"] = day.get(f"{prefix}_rows", 0) + s["num_rows"]
        day[f"{prefix}_bytes"] = day.get(f"{prefix}_bytes", 0) + s["size"]
    return sorted(days.values(), key=lambda d: d["day"])


def rounded(rows):
    return [dict(row, revenue=round(row["revenue"], 2)) for row in rows]


def categories():
    rollup = rounded(sql(CATEGORY_QUERIES[ROLLUP]))
    raw = rounded(sql(CATEGORY_QUERIES[RAW]))
    return {"rollup": rollup, "raw": raw, "identical": rollup == raw}
