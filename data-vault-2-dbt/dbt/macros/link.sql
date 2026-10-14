{% macro link(source, hash_key, columns) %}
select
    {{ hash_key }},
    {{ columns | join(', ') }},
    min(load_date) as load_date,
    min(record_source) as record_source
from {{ ref(source) }} staged
{% if is_incremental() %}
where not exists (select 1 from {{ this }} link where link.{{ hash_key }} = staged.{{ hash_key }})
{% endif %}
group by {{ hash_key }}, {{ columns | join(', ') }}
{% endmacro %}
