from schema import TABLES, TARGET

TOTALS = {
    "base": f"SELECT count() AS events, sum(amount) AS revenue FROM {TABLES['base']}",
    "projection": f"SELECT count() AS events, sum(amount) AS revenue FROM {TABLES['projection']}",
    "view": f"SELECT countMerge(events) AS events, sumMerge(amount_sum) AS revenue FROM {TARGET}",
}

CASES = [
    {
        "id": "daily",
        "title": "Daily totals by country and device",
        "note": "Exactly the stored grouping. The projection answers the unchanged SQL, the view needs its own table and -Merge combinators.",
        "sql": "SELECT toDate(ts) AS day, country, device, count() AS events, sum(amount) AS revenue, max(amount) AS max_amount "
               "FROM {table} GROUP BY day, country, device ORDER BY day, country, device",
        "view_sql": "SELECT day, country, device, countMerge(events) AS events, sumMerge(amount_sum) AS revenue, maxMerge(amount_max) AS max_amount "
                    f"FROM {TARGET} GROUP BY day, country, device ORDER BY day, country, device",
    },
    {
        "id": "country",
        "title": "Revenue by country",
        "note": "A coarser grouping over stored keys. Both re-aggregate the small pre-aggregated rows.",
        "sql": "SELECT country, count() AS events, sum(amount) AS revenue FROM {table} GROUP BY country ORDER BY country",
        "view_sql": f"SELECT country, countMerge(events) AS events, sumMerge(amount_sum) AS revenue FROM {TARGET} GROUP BY country ORDER BY country",
    },
    {
        "id": "one_country",
        "title": "One country per day",
        "note": "A filter on a stored key. Still served from the pre-aggregated rows.",
        "sql": "SELECT toDate(ts) AS day, count() AS events, sum(amount) AS revenue FROM {table} WHERE country = 'BR' GROUP BY day ORDER BY day",
        "view_sql": f"SELECT day, countMerge(events) AS events, sumMerge(amount_sum) AS revenue FROM {TARGET} WHERE country = 'BR' GROUP BY day ORDER BY day",
    },
    {
        "id": "event_type",
        "title": "Revenue by event type",
        "note": "event_type is not stored in the projection or the view target. The projection table silently falls back to a full scan, the view target cannot answer at all so the base table is queried.",
        "sql": "SELECT event_type, count() AS events, sum(amount) AS revenue FROM {table} GROUP BY event_type ORDER BY event_type",
        "view_sql": None,
    },
    {
        "id": "user_range",
        "title": "Revenue by country for users below 500",
        "note": "A filter on user_id, which is not stored pre-aggregated. Every variant reads base rows through the primary key (user_id, ts).",
        "sql": "SELECT country, count() AS events, sum(amount) AS revenue FROM {table} WHERE user_id < 500 GROUP BY country ORDER BY country",
        "view_sql": None,
    },
]


def sql_for(case, variant):
    if variant == "view" and case["view_sql"]:
        return case["view_sql"]
    return case["sql"].format(table=TABLES[variant])
