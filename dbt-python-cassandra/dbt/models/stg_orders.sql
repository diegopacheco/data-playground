select
    order_id,
    customer,
    product,
    lower(trim(category)) as category,
    quantity,
    price,
    ts
from {{ ref('orders') }}
