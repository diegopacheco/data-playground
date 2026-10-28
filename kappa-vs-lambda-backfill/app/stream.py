from psycopg import sql

import rules


def apply(cur, events, logic, view, seen, skip=frozenset()):
    firsts = {}
    for _, e in events:
        if e["event_id"] not in skip:
            firsts.setdefault(e["event_id"], e)
    if not firsts:
        return 0
    cur.execute(
        sql.SQL("INSERT INTO {} (event_id) SELECT unnest(%s::text[]) ON CONFLICT DO NOTHING RETURNING event_id").format(sql.Identifier(seen)),
        [list(firsts)],
    )
    fresh = [firsts[r[0]] for r in cur.fetchall()]
    rows = [(day, store, *values) for (day, store), values in rules.aggregate(fresh, logic).items()]
    cur.executemany(
        sql.SQL(
            "INSERT INTO {} AS t (day, store, sales, refunds, revenue_cents) VALUES (%s, %s, %s, %s, %s) "
            "ON CONFLICT (day, store) DO UPDATE SET sales = t.sales + EXCLUDED.sales, "
            "refunds = t.refunds + EXCLUDED.refunds, revenue_cents = t.revenue_cents + EXCLUDED.revenue_cents"
        ).format(sql.Identifier(view)),
        rows,
    )
    return len(fresh)
