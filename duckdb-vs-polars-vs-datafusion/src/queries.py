START = "2026-03-01 00:00:00"
END = "2026-06-01 00:00:00"

SQL = {
    "q1": """SELECT category, COUNT(*) AS orders, SUM(quantity) AS quantity, SUM(quantity * price_cents) AS revenue_cents
FROM orders GROUP BY category ORDER BY category""",
    "q2": """SELECT customer, SUM(quantity * price_cents) AS revenue_cents
FROM orders GROUP BY customer ORDER BY revenue_cents DESC, customer LIMIT 10""",
    "q3": f"""SELECT CAST(ts AS DATE) AS day, category, SUM(quantity * price_cents) AS revenue_cents
FROM orders WHERE ts >= TIMESTAMP '{START}' AND ts < TIMESTAMP '{END}'
GROUP BY CAST(ts AS DATE), category ORDER BY day, category""",
    "q4": """SELECT p.supplier, COUNT(*) AS orders, COUNT(DISTINCT o.customer) AS customers, SUM(o.quantity * o.price_cents) AS revenue_cents
FROM orders o JOIN products p ON o.product = p.product GROUP BY p.supplier ORDER BY p.supplier""",
}

COLUMNS = {
    "q1": ["category", "orders", "quantity", "revenue_cents"],
    "q2": ["customer", "revenue_cents"],
    "q3": ["day", "category", "revenue_cents"],
    "q4": ["supplier", "orders", "customers", "revenue_cents"],
}

TITLES = {
    "q1": "Per-category aggregates",
    "q2": "Top 10 customers by revenue",
    "q3": "Daily revenue by category, Mar-May 2026",
    "q4": "Join with products dimension, by supplier",
}
