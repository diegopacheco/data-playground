{{ config(materialized='incremental', unique_key='order_id', incremental_strategy='delete+insert') }}

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
FROM {{ ref('stg_orders') }}
{% if is_incremental() %}
WHERE ts > (SELECT coalesce(max(ts), TIMESTAMP '1900-01-01') FROM {{ this }})
{% endif %}
