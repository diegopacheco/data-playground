select
    order_id,
    cast(line_no as integer) as line_no,
    product_id,
    cast(quantity as integer) as quantity,
    cast(unit_price as decimal(10,2)) as unit_price,
    {{ hash_key(['order_id']) }} as order_hk,
    {{ hash_key(['product_id']) }} as product_hk,
    {{ hash_key(['order_id', 'product_id', 'line_no']) }} as order_line_hk,
    {{ hashdiff(['quantity', 'unit_price']) }} as order_line_hashdiff,
    {{ load_metadata('shop.order_lines') }}
from {{ delivery('order_lines') }}
