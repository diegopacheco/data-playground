with r as (
  select sum(total_orders) as n, sum(total_revenue) as revenue from {{ ref('revenue_by_category') }}
),
f as (
  select count(*) as n, cast(sum(amount) as decimal(14,2)) as revenue from {{ ref('fct_orders') }}
)
select r.n, f.n, r.revenue, f.revenue
from r cross join f
where r.n <> f.n or r.revenue <> f.revenue
