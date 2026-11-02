QUERIES = {
    "totals": "SELECT COUNT(*) AS order_count, SUM(amount) AS total FROM orders",
    "customer_totals": "SELECT customer_id, COUNT(*) AS order_count, SUM(amount) AS total FROM orders GROUP BY customer_id",
    "region_revenue": "SELECT c.region, COUNT(*) AS order_count, SUM(o.amount) AS revenue FROM orders o JOIN customers c ON o.customer_id = c.customer_id GROUP BY c.region",
    "top_orders": "SELECT region, order_id, amount, rn FROM (SELECT c.region, o.order_id, o.amount, ROW_NUMBER() OVER (PARTITION BY c.region ORDER BY o.amount DESC, o.order_id) AS rn FROM orders o JOIN customers c ON o.customer_id = c.customer_id) ranked WHERE rn <= 3",
}

COLUMNS = {
    "totals": ["order_count", "total"],
    "customer_totals": ["customer_id", "order_count", "total"],
    "region_revenue": ["region", "order_count", "revenue"],
    "top_orders": ["region", "order_id", "amount", "rn"],
}

PROBE = ("SELECT (SELECT COUNT(*) FROM orders), (SELECT COALESCE(SUM(amount), 0) FROM orders), "
         "(SELECT COALESCE(SUM(order_count), 0) FROM customer_totals), (SELECT COALESCE(SUM(total), 0) FROM customer_totals), "
         "(SELECT COALESCE(SUM(revenue), 0) FROM region_revenue), (SELECT order_count FROM totals), (SELECT COALESCE(total, 0) FROM totals)")


def normalize(rows):
    return sorted([list(r) for r in rows], key=lambda r: [str(v) for v in r])
