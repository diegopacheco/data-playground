select
    product_id,
    name,
    category,
    cast(price as decimal(10,2)) as price,
    {{ hash_key(['product_id']) }} as product_hk,
    {{ hashdiff(['name', 'category', 'price']) }} as product_hashdiff,
    {{ load_metadata('catalog.products') }}
from {{ delivery('products') }}
