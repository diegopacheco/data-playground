import nessie
import trino

CATALOGS = ("initial", "dev", "main", "merged")

REVENUE_SQL = """SELECT category, count(*) AS orders, sum(quantity) AS quantity, sum(quantity * price) AS revenue
FROM {ref}.shop.orders GROUP BY category ORDER BY category"""


def revenue(ref):
    if ref not in CATALOGS:
        raise ValueError("unknown ref " + ref)
    return [{
        "category": r["category"],
        "orders": r["orders"],
        "quantity": r["quantity"],
        "revenue": r["revenue"],
    } for r in trino.query(REVENUE_SQL.format(ref=ref))]


def summary():
    refs = nessie.refs()
    names = [r["name"] for r in refs]
    return {
        "refs": refs,
        "revenue": {name: revenue(name) for name in CATALOGS if name in names},
        "log": {r["name"]: nessie.log(r["name"]) for r in refs if r["type"] == "BRANCH"},
    }
