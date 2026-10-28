RULES = {
    "v1": "revenue = sales + refunds (bug: refunds are added)",
    "v2": "revenue = sales - refunds (fix: refunds are subtracted)",
}


def revenue_delta(event, logic):
    if event["kind"] == "refund" and logic == "v2":
        return -event["amount_cents"]
    return event["amount_cents"]


def aggregate(events, logic):
    out = {}
    for e in events:
        row = out.setdefault((e["ts"][:10], e["store"]), [0, 0, 0])
        row[0 if e["kind"] == "sale" else 1] += 1
        row[2] += revenue_delta(e, logic)
    return out


def first_seen(events):
    firsts = {}
    for _, e in events:
        firsts.setdefault(e["event_id"], e)
    return list(firsts.values())


def to_rows(agg):
    return [[day, store, *values] for (day, store), values in sorted(agg.items())]
