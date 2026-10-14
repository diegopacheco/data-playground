select
    line.order_line_hk,
    line.order_hk,
    line.line_no,
    line.product_hk,
    buyer.customer_hk
from {{ ref('link_order_line') }} line
join {{ ref('link_order_customer') }} buyer on buyer.order_hk = line.order_hk
