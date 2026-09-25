select
    category,
    count(*)::bigint as total_orders,
    sum(quantity)::bigint as total_quantity,
    round(sum(quantity * price), 2)::double as total_revenue
from {{ ref('stg_orders') }}
group by category
order by category
