{{ config(schema='audit') }}
{% set feeds = {
    'hub_customer': 'stg_customers',
    'hub_product': 'stg_products',
    'hub_order': 'stg_orders',
    'link_order_customer': 'stg_orders',
    'link_order_line': 'stg_order_lines',
    'sat_customer_contact': 'stg_customers',
    'sat_customer_profile': 'stg_customers',
    'sat_product': 'stg_products',
    'sat_order': 'stg_orders',
    'sat_order_line': 'stg_order_lines'
} %}
select *
from (
    {% for table, feed in feeds.items() %}
    select
        cast('{{ var("load_date") }}' as date) as load_date,
        {{ loop.index }} as position,
        '{{ table }}' as table_name,
        (select count(*) from {{ ref(feed) }}) as delivered_rows,
        (select count(*) from {{ ref(table) }}) as total_rows
    {% if not loop.last %}union all{% endif %}
    {% endfor %}
) audit
{% if is_incremental() %}
where load_date not in (select load_date from {{ this }})
{% endif %}
