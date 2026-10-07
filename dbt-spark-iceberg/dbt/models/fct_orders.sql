{{ config(materialized='incremental', incremental_strategy='merge', unique_key='order_id') }}

select
  order_id,
  customer,
  product,
  category,
  quantity,
  price,
  amount,
  ts,
  current_timestamp() as loaded_at
from {{ ref('stg_orders') }}
{% if is_incremental() %}
where ts >= (select max(ts) from {{ this }})
{% endif %}
