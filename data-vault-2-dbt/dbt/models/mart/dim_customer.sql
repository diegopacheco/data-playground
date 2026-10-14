select customer_hk, customer_id, name, email, city, segment
from {{ ref('customer_as_of') }}
where as_of_date = (select max(as_of_date) from {{ ref('pit_customer') }})
