select hub.product_hk, hub.product_id, sat.name, sat.category, sat.price
from {{ ref('hub_product') }} hub
join ({{ current_rows(ref('sat_product'), 'product_hk') }}) sat on sat.product_hk = hub.product_hk
