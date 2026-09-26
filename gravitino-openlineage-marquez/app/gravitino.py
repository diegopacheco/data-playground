import json
import os
from urllib.error import HTTPError
from urllib.parse import urlparse, quote
from urllib.request import Request, urlopen
from model import METALAKE, CATALOG, CATALOG_COMMENT, GROUPS, TAGS, SCHEMAS, TABLES, full_name

GRAVITINO_URL = os.environ.get("GRAVITINO_URL", "http://localhost:27100")
PG_DSN = os.environ.get("PG_DSN", "postgresql://shop:shop@localhost:27103/shop")
LAKE = f"/metalakes/{METALAKE}"


def call(method, path, body=None, missing_ok=False):
    data = json.dumps(body).encode() if body is not None else None
    request = Request(f"{GRAVITINO_URL}/api{path}", data=data, method=method,
                      headers={"Accept": "application/vnd.gravitino.v1+json", "Content-Type": "application/json"})
    try:
        with urlopen(request, timeout=30) as response:
            return json.load(response)
    except HTTPError as e:
        if missing_ok and e.code == 404:
            return None
        raise RuntimeError(f"gravitino {method} {path} failed with {e.code}: {error_message(e)}") from e


def error_message(e):
    raw = e.read().decode()
    try:
        return json.loads(raw).get("message", raw)
    except ValueError:
        return raw


def version():
    return call("GET", "/version")["version"]["version"]


def ensure(path, create_path, body):
    if call("GET", path, missing_ok=True) is not None:
        return "exists"
    call("POST", create_path, body)
    return "created"


def catalog_properties():
    dsn = urlparse(PG_DSN)
    database = dsn.path.lstrip("/")
    return {
        "jdbc-url": f"jdbc:postgresql://{dsn.hostname}:{dsn.port}/{database}",
        "jdbc-driver": "org.postgresql.Driver",
        "jdbc-database": database,
        "jdbc-user": dsn.username,
        "jdbc-password": dsn.password,
    }


def object_tags(kind, name):
    tags = call("GET", f"{LAKE}/objects/{kind}/{quote(name)}/tags?details=true")["tags"]
    return sorted(t["name"] for t in tags if not t.get("inherited"))


def attach_tags(kind, name, tags):
    missing = [t for t in tags if t not in object_tags(kind, name)]
    if missing:
        call("POST", f"{LAKE}/objects/{kind}/{quote(name)}/tags", {"tagsToAdd": missing})
    return missing


def owner(kind, name):
    found = call("GET", f"{LAKE}/owners/{kind}/{quote(name)}", missing_ok=True)
    return found["owner"] if found and found.get("owner") else None


def set_owner(kind, name, group):
    call("PUT", f"{LAKE}/owners/{kind}/{quote(name)}", {"name": group, "type": "GROUP"})


def table_body(t):
    columns = [{"name": c["name"], "type": c["type"], "comment": c["comment"], "nullable": c["name"] != "order_id"}
               for c in t["columns"]]
    return {"name": t["name"], "comment": t["comment"], "columns": columns, "properties": {}}


def metalakes():
    return [m["name"] for m in call("GET", "/metalakes")["metalakes"]]


def ensure_metalake():
    if METALAKE in metalakes():
        return "exists"
    call("POST", "/metalakes", {"name": METALAKE, "comment": "shop metadata lake", "properties": {}})
    return "created"


def ensure_catalog():
    steps = [("metalake", METALAKE, ensure_metalake())]
    for group in GROUPS:
        steps.append(("group", group, ensure(f"{LAKE}/groups/{group}", f"{LAKE}/groups", {"name": group})))
    for tag, comment in TAGS.items():
        steps.append(("tag", tag, ensure(f"{LAKE}/tags/{tag}", f"{LAKE}/tags", {"name": tag, "comment": comment, "properties": {}})))
    steps.append(("catalog", CATALOG, ensure(f"{LAKE}/catalogs/{CATALOG}", f"{LAKE}/catalogs", {
        "name": CATALOG, "type": "RELATIONAL", "provider": "jdbc-postgresql",
        "comment": CATALOG_COMMENT, "properties": catalog_properties()})))
    for s in SCHEMAS:
        name = f"{CATALOG}.{s['name']}"
        steps.append(("schema", name, ensure(f"{LAKE}/catalogs/{CATALOG}/schemas/{s['name']}", f"{LAKE}/catalogs/{CATALOG}/schemas",
                                             {"name": s["name"], "comment": s["comment"], "properties": {}})))
        set_owner("schema", name, s["owner"])
        attach_tags("schema", name, s["tags"])
    for t in TABLES:
        base = f"{LAKE}/catalogs/{CATALOG}/schemas/{t['schema']}/tables"
        steps.append(("table", full_name(t), ensure(f"{base}/{t['name']}", base, table_body(t))))
        set_owner("table", full_name(t), t["owner"])
        attach_tags("table", full_name(t), t["tags"])
        for c in t["columns"]:
            attach_tags("column", f"{full_name(t)}.{c['name']}", c["tags"])
    return steps


def load_table(schema, name, catalog=CATALOG):
    return call("GET", f"{LAKE}/catalogs/{catalog}/schemas/{schema}/tables/{name}")["table"]


def names(identifiers):
    return sorted(i["name"] for i in identifiers)


def table_node(catalog, schema, name):
    t = load_table(schema, name, catalog)
    full = f"{catalog}.{schema}.{name}"
    return {
        "name": name, "full_name": full, "comment": t.get("comment"), "owner": owner("table", full),
        "tags": object_tags("table", full), "created": t["audit"]["createTime"],
        "columns": [{"name": c["name"], "type": c["type"], "comment": c.get("comment"),
                     "tags": object_tags("column", f"{full}.{c['name']}")} for c in t["columns"]],
    }


def schema_node(catalog, name):
    s = call("GET", f"{LAKE}/catalogs/{catalog}/schemas/{name}")["schema"]
    full = f"{catalog}.{name}"
    tables = names(call("GET", f"{LAKE}/catalogs/{catalog}/schemas/{name}/tables")["identifiers"])
    return {"name": name, "comment": s.get("comment"), "owner": owner("schema", full), "tags": object_tags("schema", full),
            "tables": [table_node(catalog, name, t) for t in tables]}


def tree():
    if METALAKE not in metalakes():
        return None
    lake = call("GET", LAKE)
    catalogs = []
    for name in names(call("GET", f"{LAKE}/catalogs")["identifiers"]):
        c = call("GET", f"{LAKE}/catalogs/{name}")["catalog"]
        schemas = names(call("GET", f"{LAKE}/catalogs/{name}/schemas")["identifiers"])
        catalogs.append({"name": name, "provider": c["provider"], "comment": c.get("comment"),
                         "jdbc_url": c["properties"].get("jdbc-url"), "owner": owner("catalog", name),
                         "schemas": [schema_node(name, s) for s in schemas]})
    return {
        "metalake": METALAKE, "comment": lake["metalake"].get("comment"), "owner": owner("metalake", METALAKE),
        "groups": sorted(call("GET", f"{LAKE}/groups")["names"]),
        "tags": [{"name": t, "comment": call("GET", f"{LAKE}/tags/{t}")["tag"].get("comment")}
                 for t in sorted(call("GET", f"{LAKE}/tags")["names"])],
        "catalogs": catalogs,
    }
