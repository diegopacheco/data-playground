{% test unique_per_load(model, column_name) %}
select {{ column_name }}, load_date
from {{ model }}
group by {{ column_name }}, load_date
having count(*) > 1
{% endtest %}
