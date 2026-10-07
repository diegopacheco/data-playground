{% macro reset_schema() %}
  {% do run_query('create namespace if not exists ' ~ target.schema) %}
  {% set tables = run_query('show tables in ' ~ target.schema) %}
  {% for row in tables.rows %}
    {% do run_query('drop table if exists ' ~ target.schema ~ '.' ~ row[1] ~ ' purge') %}
  {% endfor %}
  {% do run_query('drop namespace if exists ' ~ target.schema) %}
  {% do log('dropped namespace ' ~ target.schema ~ ' and ' ~ tables.rows | length ~ ' tables', info=true) %}
{% endmacro %}
