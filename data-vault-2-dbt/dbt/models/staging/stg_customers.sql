select
    customer_id,
    name,
    email,
    city,
    segment,
    {{ hash_key(['customer_id']) }} as customer_hk,
    {{ hashdiff(['name', 'email']) }} as contact_hashdiff,
    {{ hashdiff(['city', 'segment']) }} as profile_hashdiff,
    {{ load_metadata('crm.customers') }}
from {{ delivery('customers') }}
