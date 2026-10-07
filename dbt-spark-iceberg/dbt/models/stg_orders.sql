select
  order_id,
  customer,
  product,
  lower(category) as category,
  quantity,
  price,
  cast(quantity * price as decimal(12,2)) as amount,
  ts
from {{ ref('orders') }}
where ts <= timestamp '{{ var("cutoff") }}'
