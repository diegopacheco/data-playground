select
    order_id,
    customer_id,
    cast(order_date as date) as order_date,
    status,
    {{ hash_key(['order_id']) }} as order_hk,
    {{ hash_key(['customer_id']) }} as customer_hk,
    {{ hash_key(['order_id', 'customer_id']) }} as order_customer_hk,
    {{ hashdiff(['order_date', 'status']) }} as order_hashdiff,
    {{ load_metadata('shop.orders') }}
from {{ delivery('orders') }}
