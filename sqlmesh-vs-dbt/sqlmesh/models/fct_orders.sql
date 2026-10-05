MODEL (
  name sales.fct_orders,
  kind INCREMENTAL_BY_TIME_RANGE (
    time_column ts
  ),
  cron '@daily',
  grain order_id,
  audits (
    unique_values(columns := (order_id)),
    not_null(columns := (order_id, order_date, revenue)),
    assert_non_negative(column := revenue)
  )
);

SELECT
  order_id,
  ts,
  ts::DATE AS order_date,
  customer,
  product,
  category,
  quantity,
  price,
  (quantity * price)::DECIMAL(12, 2) AS revenue
FROM sales.stg_orders
WHERE ts BETWEEN @start_ts AND @end_ts
