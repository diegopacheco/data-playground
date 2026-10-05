MODEL (
  name sales.stg_orders,
  kind FULL,
  grain order_id,
  audits (
    unique_values(columns := (order_id)),
    not_null(columns := (order_id, category, quantity, price, ts))
  )
);

SELECT
  order_id::INT AS order_id,
  trim(customer) AS customer,
  trim(product) AS product,
  lower(trim(category)) AS category,
  quantity::INT AS quantity,
  price::DECIMAL(10, 2) AS price,
  strptime(ts, '%Y-%m-%dT%H:%M:%SZ') AS ts
FROM raw.orders
