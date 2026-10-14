{% macro delivery(file) %}
read_csv('{{ var("data_dir") }}/{{ var("load_date") }}/{{ file }}.csv', header = true, all_varchar = true)
{% endmacro %}

{% macro load_metadata(record_source) %}
cast('{{ var("load_date") }}' as date) as load_date,
'{{ record_source }}' as record_source
{% endmacro %}
