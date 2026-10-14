select
    dates.as_of_date,
    hub.customer_hk,
    hub.customer_id,
    (select max(load_date) from {{ ref('sat_customer_contact') }} sat
        where sat.customer_hk = hub.customer_hk and sat.load_date <= dates.as_of_date) as contact_load_date,
    (select max(load_date) from {{ ref('sat_customer_profile') }} sat
        where sat.customer_hk = hub.customer_hk and sat.load_date <= dates.as_of_date) as profile_load_date
from {{ ref('hub_customer') }} hub
join (select distinct load_date as as_of_date from {{ ref('load_audit') }}) dates
    on hub.load_date <= dates.as_of_date
