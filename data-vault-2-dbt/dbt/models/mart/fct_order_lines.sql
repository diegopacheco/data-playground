select
    bridge.order_line_hk,
    bridge.customer_hk,
    bridge.product_hk,
    hub.order_id,
    bridge.line_no,
    header.order_date,
    header.status,
    line.quantity,
    line.unit_price,
    line.quantity * line.unit_price as revenue
from {{ ref('bridge_order_line') }} bridge
join {{ ref('hub_order') }} hub on hub.order_hk = bridge.order_hk
join ({{ current_rows(ref('sat_order'), 'order_hk') }}) header on header.order_hk = bridge.order_hk
join ({{ current_rows(ref('sat_order_line'), 'order_line_hk') }}) line on line.order_line_hk = bridge.order_line_hk
