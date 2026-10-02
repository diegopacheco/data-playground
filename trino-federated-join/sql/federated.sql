SELECT
  c.region,
  p.category,
  p.supplier,
  count(*) AS orders,
  sum(o.quantity) AS units,
  round(sum(o.quantity * o.price), 2) AS revenue,
  round(sum(o.quantity * p.cost), 2) AS cost,
  round(sum(o.quantity * o.price) - sum(o.quantity * p.cost), 2) AS margin,
  round(100 * (sum(o.quantity * o.price) - sum(o.quantity * p.cost)) / sum(o.quantity * o.price), 2) AS margin_pct
FROM cassandra.sales.orders o
JOIN postgres.public.customers c ON o.customer = c.customer_name
JOIN iceberg.lake.products p ON o.product = p.product
GROUP BY c.region, p.category, p.supplier
ORDER BY c.region, p.category, p.supplier
