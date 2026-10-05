MODEL (
  name sales.revenue_by_category,
  kind FULL,
  grain category,
  audits (
    unique_values(columns := (category)),
    not_null(columns := (category, total_revenue)),
    assert_non_negative(column := total_revenue)
  )
);

SELECT
  category,
  COUNT(*)::BIGINT AS total_orders,
  SUM(quantity)::BIGINT AS total_quantity,
  SUM(revenue)::DECIMAL(14, 2) AS total_revenue
FROM sales.fct_orders
GROUP BY category
