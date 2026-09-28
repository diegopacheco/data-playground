import csv
import json
import os
import time
from pathlib import Path
import psycopg

DSN = os.environ.get("DATABASE_URL", "postgresql://graph:graph@r15-age:5432/graph")
DATA = Path(os.environ.get("DATA_DIR", "/data"))
GRAPH = "shop"
MAX_HOPS = 6

TABLES = {
    "customers": ("customer_id int PRIMARY KEY, name text NOT NULL, city text NOT NULL", "customers.csv"),
    "products": ("product_id int PRIMARY KEY, name text NOT NULL, category text NOT NULL, price_cents int NOT NULL", "products.csv"),
    "follows": ("follower_id int REFERENCES sales.customers, followed_id int REFERENCES sales.customers, PRIMARY KEY (follower_id, followed_id)", "follows.csv"),
    "orders": ("order_id int PRIMARY KEY, customer_id int REFERENCES sales.customers, product_id int REFERENCES sales.products, quantity int NOT NULL, price_cents int NOT NULL, order_date date NOT NULL", "orders.csv"),
}

KHOP = """MATCH p = (c:Customer {id: %(customer)d})-[:FOLLOWS*1..%(k)d]->(n:Customer)
WHERE n.id <> %(customer)d
RETURN n.id, n.name, min(length(p))"""

PATH = """MATCH p = (a:Customer {id: %(source)d})-[:FOLLOWS*1..%(max)d]->(b:Customer {id: %(target)d})
RETURN [n IN nodes(p) | n.id], length(p)
ORDER BY length(p)
LIMIT 1"""

RECOMMEND = """MATCH (x:Product {id: %(product)d})<-[:BOUGHT]-(c:Customer)-[:BOUGHT]->(o:Product)
WHERE o.id <> %(product)d
RETURN o.id, o.name, o.category, count(DISTINCT c)"""

BUYERS = """MATCH (x:Product {id: %(product)d})<-[:BOUGHT]-(c:Customer)
RETURN c.id, c.name"""

NETWORK = """MATCH (c:Customer {id: %(customer)d})-[:FOLLOWS*1..%(k)d]->(n:Customer)
WHERE n.id <> %(customer)d
RETURN DISTINCT n.id"""

SPEND_SQL = """SELECT p.category, count(DISTINCT o.customer_id) AS customers, count(*) AS order_lines,
       sum(o.quantity * o.price_cents) AS revenue_cents
FROM cypher('shop', $$ {cypher} $$) AS g(customer_id agtype)
JOIN sales.orders o ON o.customer_id = g.customer_id::int
JOIN sales.products p ON p.product_id = o.product_id
GROUP BY p.category
ORDER BY revenue_cents DESC, p.category"""

PICKS_SQL = """SELECT p.product_id, p.name, p.category, count(DISTINCT o.customer_id) AS buyers
FROM cypher('shop', $$ {cypher} $$) AS g(customer_id agtype)
JOIN sales.orders o ON o.customer_id = g.customer_id::int
JOIN sales.products p ON p.product_id = o.product_id
WHERE NOT EXISTS (SELECT 1 FROM sales.orders mine WHERE mine.customer_id = %(customer)s AND mine.product_id = p.product_id)
GROUP BY p.product_id, p.name, p.category
ORDER BY buyers DESC, p.product_id
LIMIT 5"""


def connect():
    conn = psycopg.connect(DSN, autocommit=True)
    conn.execute("LOAD 'age'")
    conn.execute("SET search_path = ag_catalog, \"$user\", public")
    return conn


def wait_ready(tries=60):
    for _ in range(tries):
        try:
            connect().close()
            return
        except psycopg.OperationalError:
            time.sleep(1)
    raise RuntimeError(f"database not reachable at {DSN}")


def value(raw):
    if raw is None:
        return None
    return json.loads(raw)


def cypher(conn, text, columns):
    cols = ", ".join(f"c{i} agtype" for i in range(columns))
    rows = conn.execute(f"SELECT * FROM cypher('{GRAPH}', $$ {text} $$) AS ({cols})").fetchall()
    return [[value(v) for v in row] for row in rows]


def literal(v):
    if isinstance(v, str):
        return "'" + v.replace("\\", "\\\\").replace("'", "\\'") + "'"
    return str(v)


def unwind(conn, rows, body):
    if not rows:
        return
    items = ", ".join("{" + ", ".join(f"{k}: {literal(v)}" for k, v in r.items()) + "}" for r in rows)
    conn.execute(f"SELECT * FROM cypher('{GRAPH}', $$ UNWIND [{items}] AS r {body} $$) AS (x agtype)")


def load():
    started = time.time()
    with connect() as conn:
        conn.execute("CREATE EXTENSION IF NOT EXISTS age")
        if conn.execute("SELECT 1 FROM ag_graph WHERE name = %s", (GRAPH,)).fetchone():
            conn.execute("SELECT drop_graph(%s, true)", (GRAPH,))
        conn.execute("DROP SCHEMA IF EXISTS sales CASCADE")
        conn.execute("CREATE SCHEMA sales")
        for table, (ddl, file) in TABLES.items():
            conn.execute(f"CREATE TABLE sales.{table} ({ddl})")
            with open(DATA / file) as f, conn.cursor().copy(f"COPY sales.{table} FROM STDIN WITH (FORMAT csv, HEADER true)") as copy:
                copy.write(f.read())
        conn.execute("SELECT create_graph(%s)", (GRAPH,))
        customers = conn.execute("SELECT customer_id AS id, name, city FROM sales.customers ORDER BY 1").fetchall()
        unwind(conn, [dict(zip(("id", "name", "city"), r)) for r in customers], "CREATE (:Customer {id: r.id, name: r.name, city: r.city})")
        products = conn.execute("SELECT product_id, name, category, price_cents FROM sales.products ORDER BY 1").fetchall()
        unwind(conn, [dict(zip(("id", "name", "category", "price"), r)) for r in products], "CREATE (:Product {id: r.id, name: r.name, category: r.category, price_cents: r.price})")
        follows = conn.execute("SELECT follower_id, followed_id FROM sales.follows ORDER BY 1, 2").fetchall()
        unwind(conn, [{"a": a, "b": b} for a, b in follows], "MATCH (a:Customer {id: r.a}), (b:Customer {id: r.b}) CREATE (a)-[:FOLLOWS]->(b)")
        bought = conn.execute("SELECT customer_id, product_id, count(*), sum(quantity) FROM sales.orders GROUP BY 1, 2 ORDER BY 1, 2").fetchall()
        unwind(conn, [{"c": c, "p": p, "n": n, "q": q} for c, p, n, q in bought], "MATCH (c:Customer {id: r.c}), (p:Product {id: r.p}) CREATE (c)-[:BOUGHT {orders: r.n, quantity: r.q}]->(p)")
    return {"seconds": round(time.time() - started, 3), **stats()}


def stats():
    with connect() as conn:
        nodes = {label: n for label, n in cypher(conn, "MATCH (n) RETURN label(n), count(*)", 2)}
        edges = {label: n for label, n in cypher(conn, "MATCH ()-[e]->() RETURN label(e), count(*)", 2)}
        tables = {t: conn.execute(f"SELECT count(*) FROM sales.{t}").fetchone()[0] for t in TABLES}
        versions = conn.execute("SELECT (SELECT extversion FROM pg_extension WHERE extname = 'age'), split_part(current_setting('server_version'), ' ', 1)").fetchone()
    return {"nodes": nodes, "edges": edges, "tables": tables, "age": versions[0], "postgres": versions[1]}


def graph():
    with connect() as conn:
        customers = cypher(conn, "MATCH (n:Customer) RETURN n.id, n.name, n.city ORDER BY n.id", 3)
        products = cypher(conn, "MATCH (n:Product) RETURN n.id, n.name, n.category, n.price_cents ORDER BY n.id", 4)
        follows = cypher(conn, "MATCH (a:Customer)-[:FOLLOWS]->(b:Customer) RETURN a.id, b.id", 2)
        bought = cypher(conn, "MATCH (c:Customer)-[e:BOUGHT]->(p:Product) RETURN c.id, p.id, e.orders, e.quantity", 4)
    nodes = [{"key": f"c{i}", "id": i, "type": "Customer", "name": n, "city": c} for i, n, c in customers]
    nodes += [{"key": f"p{i}", "id": i, "type": "Product", "name": n, "category": c, "price_cents": pr} for i, n, c, pr in products]
    edges = [{"type": "FOLLOWS", "from": f"c{a}", "to": f"c{b}"} for a, b in follows]
    edges += [{"type": "BOUGHT", "from": f"c{c}", "to": f"p{p}", "orders": n, "quantity": q} for c, p, n, q in bought]
    return {"nodes": nodes, "edges": edges}


def khop(customer, k):
    text = KHOP % {"customer": customer, "k": k}
    with connect() as conn:
        rows = cypher(conn, text, 3)
    reached = sorted(({"id": i, "name": n, "hops": h} for i, n, h in rows), key=lambda r: (r["hops"], r["id"]))
    return {"customer": customer, "k": k, "cypher": text, "reached": reached}


def shortest_path(source, target):
    text = PATH % {"source": source, "target": target, "max": MAX_HOPS}
    if source == target:
        return {"from": source, "to": target, "cypher": text, "path": [source], "hops": 0}
    with connect() as conn:
        rows = cypher(conn, text, 2)
    path, hops = (rows[0][0], rows[0][1]) if rows else (None, None)
    return {"from": source, "to": target, "max_hops": MAX_HOPS, "cypher": text, "path": path, "hops": hops}


def recommend(product):
    text = RECOMMEND % {"product": product}
    with connect() as conn:
        buyers = cypher(conn, BUYERS % {"product": product}, 2)
        rows = cypher(conn, text, 4)
    rows.sort(key=lambda r: (-r[3], r[0]))
    return {"product": product, "cypher": text, "buyers": sorted(b[0] for b in buyers),
            "also_bought": [{"id": i, "name": n, "category": c, "buyers": b} for i, n, c, b in rows[:5]]}


def network(customer, k):
    inner = " ".join((NETWORK % {"customer": customer, "k": k}).split())
    spend_sql = SPEND_SQL.format(cypher=inner)
    picks_sql = PICKS_SQL.format(cypher=inner)
    with connect() as conn:
        spend = conn.execute(spend_sql).fetchall()
        picks = conn.execute(picks_sql, {"customer": customer}).fetchall()
    return {"customer": customer, "k": k, "sql": [spend_sql, picks_sql.replace("%(customer)s", str(customer))],
            "spend": [{"category": c, "customers": n, "order_lines": l, "revenue_cents": int(r)} for c, n, l, r in spend],
            "picks": [{"id": i, "name": n, "category": c, "buyers": b} for i, n, c, b in picks]}
