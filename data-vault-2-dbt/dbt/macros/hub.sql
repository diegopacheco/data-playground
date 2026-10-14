{% macro hub(source, hash_key, business_key) %}
select
    {{ hash_key }},
    {{ business_key }},
    min(load_date) as load_date,
    min(record_source) as record_source
from {{ ref(source) }} staged
{% if is_incremental() %}
where not exists (select 1 from {{ this }} hub where hub.{{ hash_key }} = staged.{{ hash_key }})
{% endif %}
group by {{ hash_key }}, {{ business_key }}
{% endmacro %}
