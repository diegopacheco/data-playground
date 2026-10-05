SELECT
  order_date,
  COUNT(*)::BIGINT AS total_orders,
  SUM(revenue)::DECIMAL(14, 2) AS revenue
FROM {{ ref('fct_orders') }}
GROUP BY order_date
