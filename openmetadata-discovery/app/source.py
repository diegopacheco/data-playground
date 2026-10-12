import os
import psycopg2

PG = {
    "host": os.environ.get("PG_HOST", "r14-postgres"),
    "port": int(os.environ.get("PG_PORT", "5432")),
    "dbname": os.environ.get("PG_DATABASE", "shop"),
    "user": os.environ.get("PG_USER", "om_reader"),
    "password": os.environ.get("PG_PASSWORD", "om_reader_password"),
}

TABLES = """
SELECT n.nspname, c.relname, c.relkind, obj_description(c.oid, 'pg_class')
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = ANY(%s) AND c.relkind IN ('r', 'v')
ORDER BY 1, 2
"""

COLUMNS = """
SELECT n.nspname, c.relname, a.attname, format_type(a.atttypid, a.atttypmod), col_description(c.oid, a.attnum)
FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = ANY(%s) AND c.relkind IN ('r', 'v') AND a.attnum > 0 AND NOT a.attisdropped
ORDER BY 1, 2, a.attnum
"""

VIEW_DEPENDENCIES = """
SELECT DISTINCT sn.nspname || '.' || s.relname, vn.nspname || '.' || v.relname
FROM pg_depend d
JOIN pg_rewrite r ON r.oid = d.objid
JOIN pg_class v ON v.oid = r.ev_class
JOIN pg_namespace vn ON vn.oid = v.relnamespace
JOIN pg_class s ON s.oid = d.refobjid
JOIN pg_namespace sn ON sn.oid = s.relnamespace
WHERE d.classid = 'pg_rewrite'::regclass AND d.refclassid = 'pg_class'::regclass
  AND v.oid <> s.oid AND vn.nspname = ANY(%s) AND sn.nspname = ANY(%s)
ORDER BY 1, 2
"""


def query(sql, *params):
    with psycopg2.connect(**PG) as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def snapshot(schemas):
    tables = {}
    for schema, name, kind, description in query(TABLES, schemas):
        tables[f"{schema}.{name}"] = {"schema": schema, "name": name, "type": "View" if kind == "v" else "Regular", "description": description, "columns": []}
    for schema, table, column, data_type, description in query(COLUMNS, schemas):
        tables[f"{schema}.{table}"]["columns"].append({"name": column, "dataType": data_type, "description": description})
    edges = [{"from": a, "to": b} for a, b in query(VIEW_DEPENDENCIES, schemas, schemas)]
    return {"tables": tables, "viewLineage": edges}
