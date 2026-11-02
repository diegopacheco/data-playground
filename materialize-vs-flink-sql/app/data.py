import json
import random

REGIONS = ["north", "south", "east", "west"]
STATUSES = ["new", "paid", "shipped"]
CUSTOMERS = [f"c{i}" for i in range(1, 9)]


def customer(cid, region):
    return {"customer_id": cid, "name": f"customer {cid[1:]}", "region": region}


def order(oid, cid, amount, status):
    return {"order_id": oid, "customer_id": cid, "amount": amount, "status": status}


def phases(seed=42):
    rnd = random.Random(seed)
    regions = {cid: REGIONS[i % len(REGIONS)] for i, cid in enumerate(CUSTOMERS)}
    live = {}
    out = []

    def put(topic, key, value):
        out[-1]["events"].append({"topic": topic, "key": key, "value": value})

    out.append({"name": "customers", "events": []})
    for cid in CUSTOMERS:
        put("customers", cid, customer(cid, regions[cid]))

    out.append({"name": "inserts", "events": []})
    for oid in range(1, 61):
        live[oid] = order(oid, rnd.choice(CUSTOMERS), rnd.randint(10, 500), "new")
        put("orders", str(oid), live[oid])

    out.append({"name": "updates", "events": []})
    for _ in range(40):
        oid = rnd.choice(sorted(live))
        o = dict(live[oid])
        o["amount"] = rnd.randint(10, 900)
        o["status"] = rnd.choice(STATUSES[1:])
        if rnd.random() < 0.3:
            o["customer_id"] = rnd.choice(CUSTOMERS)
        live[oid] = o
        put("orders", str(oid), o)

    out.append({"name": "moves", "events": []})
    for cid, region in [("c1", "west"), ("c6", "north")]:
        regions[cid] = region
        put("customers", cid, customer(cid, region))

    out.append({"name": "deletes", "events": []})
    deleted = rnd.sample(sorted(live), 15)
    for oid in deleted:
        del live[oid]
        put("orders", str(oid), None)
    put("orders", "999", None)

    out.append({"name": "reinserts", "events": []})
    for oid in sorted(deleted)[:5]:
        live[oid] = order(oid, rnd.choice(CUSTOMERS), rnd.randint(10, 900), "new")
        put("orders", str(oid), live[oid])
    return out


def events(seed=42):
    return [e for p in phases(seed) for e in p["events"]]


def encode(value):
    return None if value is None else json.dumps(value, separators=(",", ":")).encode()
