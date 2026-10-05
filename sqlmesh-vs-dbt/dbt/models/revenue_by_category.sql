SELECT
  category,
  COUNT(*)::BIGINT AS total_orders,
  SUM(quantity)::BIGINT AS total_quantity,
  SUM(revenue)::DECIMAL(14, 2) AS total_revenue
FROM {{ ref('fct_orders') }}
GROUP BY category
