{% macro satellite(source, parent_key, hashdiff, attributes) %}
with staged as (
    select distinct
        {{ parent_key }},
        {{ hashdiff }} as hashdiff,
        {{ attributes | join(', ') }},
        load_date,
        record_source
    from {{ ref(source) }}
)
select staged.*
from staged
{% if is_incremental() %}
left join ({{ current_rows(this, parent_key) }}) latest on latest.{{ parent_key }} = staged.{{ parent_key }}
where latest.hashdiff is null or latest.hashdiff <> staged.hashdiff
{% endif %}
{% endmacro %}

{% macro current_rows(relation, key) %}
select * from {{ relation }}
qualify row_number() over (partition by {{ key }} order by load_date desc) = 1
{% endmacro %}
