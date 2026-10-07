with seed as (
  select count(*) as n, cast(sum(quantity * price) as decimal(14,2)) as revenue
  from {{ ref('orders') }}
  where ts <= timestamp '{{ var("cutoff") }}'
),
fct as (
  select count(*) as n, cast(sum(amount) as decimal(14,2)) as revenue
  from {{ ref('fct_orders') }}
)
select seed.n, fct.n, seed.revenue, fct.revenue
from seed cross join fct
where seed.n <> fct.n or seed.revenue <> fct.revenue
