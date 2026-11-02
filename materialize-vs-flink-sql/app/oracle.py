from queries import normalize


def replay(events):
    tables = {"orders": {}, "customers": {}}
    for e in events:
        if e["value"] is None:
            tables[e["topic"]].pop(e["key"], None)
        else:
            tables[e["topic"]][e["key"]] = e["value"]
    return tables["orders"], tables["customers"]


def answers(events):
    orders, customers = replay(events)
    rows = list(orders.values())
    region = {c["customer_id"]: c["region"] for c in customers.values()}
    per_customer, per_region, ranked = {}, {}, {}
    for o in rows:
        n, s = per_customer.get(o["customer_id"], (0, 0))
        per_customer[o["customer_id"]] = (n + 1, s + o["amount"])
        if o["customer_id"] in region:
            r = region[o["customer_id"]]
            n, s = per_region.get(r, (0, 0))
            per_region[r] = (n + 1, s + o["amount"])
            ranked.setdefault(r, []).append(o)
    top = []
    for r, items in ranked.items():
        items.sort(key=lambda o: (-o["amount"], o["order_id"]))
        top += [[r, o["order_id"], o["amount"], i + 1] for i, o in enumerate(items[:3])]
    return {
        "totals": [[len(rows), sum(o["amount"] for o in rows) if rows else None]],
        "customer_totals": normalize([[c, n, s] for c, (n, s) in per_customer.items()]),
        "region_revenue": normalize([[r, n, s] for r, (n, s) in per_region.items()]),
        "top_orders": normalize(top),
    }


def totals_prefixes(events):
    live = {}
    seen = [(0, None)]
    for e in events:
        if e["topic"] != "orders":
            continue
        if e["value"] is None:
            live.pop(e["key"], None)
        else:
            live[e["key"]] = e["value"]["amount"]
        seen.append((len(live), sum(live.values()) if live else None))
    return seen


def mz_states(changelog):
    state, out = {}, []
    for ts in sorted({r[0] for r in changelog}):
        for r in changelog:
            if r[0] == ts:
                key = tuple(r[2:])
                state[key] = state.get(key, 0) + r[1]
        out.append([ts] + [list(k) for k, d in state.items() for _ in range(d) if d > 0])
    return out


def flink_states(changelog):
    state, out = [], []
    for r in changelog:
        if r[0] in ("INSERT", "UPDATE_AFTER"):
            state.append(r[1:])
            out.append([r[0]] + [list(s) for s in state])
        else:
            state.remove(r[1:])
    return out
