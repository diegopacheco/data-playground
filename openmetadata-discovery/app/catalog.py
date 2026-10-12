import os
import source
from pipeline import CURATION, fqn

PUBLIC_URL = os.environ.get("OM_PUBLIC_URL", "http://localhost:27901").rstrip("/")
PREFIX = fqn("")


def short(name):
    return name[len(PREFIX):] if name.startswith(PREFIX) else name


def tags_of(entity):
    return sorted(t["tagFQN"] for t in entity.get("tags") or [])


def table_view(t):
    return {
        "key": short(t["fullyQualifiedName"]),
        "fqn": t["fullyQualifiedName"],
        "type": t.get("tableType"),
        "description": t.get("description"),
        "tags": tags_of(t),
        "owners": sorted(f"{o['type']}:{o['name']}" for o in t.get("owners") or []),
        "columns": [{"name": c["name"], "dataType": c.get("dataType"), "dataTypeDisplay": c.get("dataTypeDisplay"), "description": c.get("description"), "tags": tags_of(c)} for c in t["columns"]],
        "url": f"{PUBLIC_URL}/table/{t['fullyQualifiedName']}",
    }


def catalog(om):
    tables = om.tables(f"{CURATION['service']}.{CURATION['database']}")
    return sorted((table_view(t) for t in tables if not t.get("deleted")), key=lambda t: t["key"])


def lineage(om, tables):
    edges = {}
    for table in tables:
        graph = om.lineage(table["fqn"])
        names = {n["id"]: n["fullyQualifiedName"] for n in graph.get("nodes", [])}
        names[graph["entity"]["id"]] = graph["entity"]["fullyQualifiedName"]
        for edge in graph.get("upstreamEdges", []) + graph.get("downstreamEdges", []):
            a, b = short(names.get(edge["fromEntity"], edge["fromEntity"])), short(names.get(edge["toEntity"], edge["toEntity"]))
            details = edge.get("lineageDetails") or {}
            edges[(a, b)] = {"from": a, "to": b, "source": details.get("source"), "sql": details.get("sqlQuery"), "description": details.get("description"), "columns": len(details.get("columnsLineage") or [])}
    return sorted(edges.values(), key=lambda e: (e["from"], e["to"]))


def verify(om):
    truth = source.snapshot(CURATION["schemas"])
    tables = {t["key"]: t for t in catalog(om)}
    edges = {(e["from"], e["to"]) for e in lineage(om, tables.values())}
    checks = []

    def check(name, ok, detail=""):
        checks.append({"check": name, "ok": bool(ok), "detail": detail})

    check("every postgres table and view is in the catalog", set(truth["tables"]) == set(tables), f"postgres {len(truth['tables'])}, catalog {len(tables)}")
    for key, t in truth["tables"].items():
        c = tables.get(key)
        if not c:
            check(f"{key} ingested", False, "missing")
            continue
        check(f"{key} type {t['type']}", c["type"] == t["type"], c["type"])
        check(f"{key} description equals COMMENT ON", c["description"] == t["description"], c["description"] or "")
        same_columns = [x["name"] for x in c["columns"]] == [x["name"] for x in t["columns"]]
        check(f"{key} columns in order", same_columns, ", ".join(x["name"] for x in c["columns"]))
        check(f"{key} column comments", same_columns and all(a["description"] == b["description"] for a, b in zip(c["columns"], t["columns"])))
    for e in truth["viewLineage"]:
        check(f"view lineage {e['from']} -> {e['to']}", (e["from"], e["to"]) in edges, "from pg_depend")
    for e in CURATION["lineage"]:
        check(f"manual lineage {e['from']} -> {e['to']}", (e["from"], e["to"]) in edges, e["description"])
    for key, spec in CURATION["tables"].items():
        c = tables.get(key, {"tags": [], "owners": [], "columns": []})
        check(f"{key} tags", c["tags"] == sorted(spec["tags"]), ", ".join(c["tags"]))
        check(f"{key} owners", c["owners"] == sorted(f"{o['type']}:{o['name']}" for o in spec["owners"]), ", ".join(c["owners"]))
        columns = {x["name"]: x["tags"] for x in c["columns"]}
        check(f"{key} column tags", all(columns.get(n) == sorted(v) for n, v in spec["columns"].items()), str({n: columns.get(n) for n in spec["columns"]}))
    return {"ok": all(c["ok"] for c in checks), "passed": sum(c["ok"] for c in checks), "total": len(checks), "checks": checks}
