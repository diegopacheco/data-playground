{% macro hash_key(columns) %}
md5(concat_ws('||'{% for c in columns %}, upper(trim(coalesce(cast({{ c }} as varchar), ''))){% endfor %}))
{% endmacro %}

{% macro hashdiff(columns) %}
md5(concat_ws('||'{% for c in columns %}, trim(coalesce(cast({{ c }} as varchar), '')){% endfor %}))
{% endmacro %}
