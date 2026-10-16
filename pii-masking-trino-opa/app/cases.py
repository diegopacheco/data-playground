from trino import attempt

USERS = ["alice", "bruno", "rita", "sam", "mallory"]
ADMIN = "alice"
PROJECTION = "customer_id, email, national_id, phone, country"
BOOTSTRAP = [
    "CREATE OR REPLACE VIEW scratch.default.customers_invoker SECURITY INVOKER AS SELECT * FROM postgres.public.customers",
    "CREATE OR REPLACE VIEW scratch.default.customers_definer SECURITY DEFINER AS SELECT * FROM postgres.public.customers",
    "DROP TABLE IF EXISTS scratch.default.customers_admin_copy",
    "CREATE TABLE scratch.default.customers_admin_copy AS SELECT * FROM postgres.public.customers",
]
CASES = {
    "columns": {
        "title": "Explicit columns",
        "sql": "SELECT customer_id, name, email, national_id, phone, country, credit_card, balance FROM customers ORDER BY customer_id LIMIT 3",
    },
    "star": {
        "title": "SELECT *",
        "sql": "SELECT * FROM customers ORDER BY customer_id LIMIT 3",
    },
    "join": {
        "title": "Join",
        "sql": "SELECT c.customer_id, c.email, c.national_id, c.country, count(*) AS orders, sum(o.amount) AS amount FROM customers c JOIN orders o ON o.customer_id = c.customer_id GROUP BY 1, 2, 3, 4 ORDER BY 1 LIMIT 3",
    },
    "orders": {
        "title": "Orders total",
        "sql": "SELECT count(*) AS orders, sum(amount) AS amount FROM orders",
    },
    "where_raw": {
        "title": "WHERE raw value",
        "sql": "SELECT count(*) AS matches FROM customers WHERE email = 'ben.001@post.test'",
    },
    "where_suffix": {
        "title": "WHERE visible suffix",
        "sql": "SELECT count(*) AS matches FROM customers WHERE national_id LIKE '%0007'",
    },
    "distinct": {
        "title": "count(DISTINCT)",
        "sql": "SELECT count(*) AS customers, count(DISTINCT email) AS emails, count(DISTINCT national_id) AS national_ids, count(DISTINCT phone) AS phones FROM customers",
    },
    "view_invoker": {
        "title": "View, SECURITY INVOKER",
        "sql": f"SELECT {PROJECTION} FROM scratch.default.customers_invoker ORDER BY customer_id LIMIT 3",
    },
    "view_definer": {
        "title": "View, SECURITY DEFINER",
        "sql": f"SELECT {PROJECTION} FROM scratch.default.customers_definer ORDER BY customer_id LIMIT 3",
    },
    "ctas": {
        "title": "CREATE TABLE AS",
        "prepare": [
            "DROP TABLE IF EXISTS scratch.default.copy_{user}",
            f"CREATE TABLE scratch.default.copy_{{user}} AS SELECT {PROJECTION} FROM customers",
        ],
        "sql": f"SELECT {PROJECTION} FROM scratch.default.copy_{{user}} ORDER BY customer_id LIMIT 3",
        "reader": ADMIN,
    },
    "admin_copy": {
        "title": "Copy made by admin",
        "sql": f"SELECT {PROJECTION} FROM scratch.default.customers_admin_copy ORDER BY customer_id LIMIT 3",
    },
}


def run(case, user):
    for statement in case.get("prepare", []):
        result = attempt(statement.format(user=user), user)
        if "error" in result:
            return result
    return attempt(case["sql"].format(user=user), case.get("reader", user))


def compare(key):
    case = CASES[key]
    results = {user: run(case, user) for user in USERS}
    for user, result in results.items():
        result["same_as_admin"] = user != ADMIN and "rows" in result and result["rows"] == results[ADMIN].get("rows")
    return {
        "case": key,
        "title": case["title"],
        "prepare": case.get("prepare", []),
        "sql": case["sql"],
        "reader": case.get("reader"),
        "results": results,
    }
