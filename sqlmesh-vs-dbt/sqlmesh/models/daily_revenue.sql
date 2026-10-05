MODEL (
  name sales.daily_revenue,
  kind FULL,
  grain order_date,
  audits (
    unique_values(columns := (order_date)),
    not_null(columns := (order_date, revenue)),
    assert_non_negative(column := revenue)
  )
);

SELECT
  order_date,
  COUNT(*)::BIGINT AS total_orders,
  SUM(revenue)::DECIMAL(14, 2) AS revenue
FROM sales.fct_orders
GROUP BY order_date
