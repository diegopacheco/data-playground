{% test changes_only(model, column_name) %}
select *
from (
    select hashdiff, lag(hashdiff) over (partition by {{ column_name }} order by load_date) as previous
    from {{ model }}
) versions
where hashdiff = previous
{% endtest %}
