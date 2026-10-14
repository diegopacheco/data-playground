{{ config(materialized='view') }}
select
    pit.as_of_date,
    pit.customer_hk,
    pit.customer_id,
    contact.name,
    contact.email,
    profile.city,
    profile.segment,
    pit.contact_load_date,
    pit.profile_load_date
from {{ ref('pit_customer') }} pit
join {{ ref('sat_customer_contact') }} contact
    on contact.customer_hk = pit.customer_hk and contact.load_date = pit.contact_load_date
join {{ ref('sat_customer_profile') }} profile
    on profile.customer_hk = pit.customer_hk and profile.load_date = pit.profile_load_date
