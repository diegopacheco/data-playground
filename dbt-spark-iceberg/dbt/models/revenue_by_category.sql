select
  category,
  count(*) as total_orders,
  sum(quantity) as total_quantity,
  cast(sum(amount) as decimal(14,2)) as total_revenue
from {{ ref('fct_orders') }}
group by category
