create table if not exists events (
  id bigint not null,
  ts timestamptz not null,
  category text not null,
  amount_cents bigint not null
) partition by range (ts);

create table if not exists daily_aggregates (
  worker text not null,
  day date not null,
  category text not null,
  event_count bigint not null,
  amount_total bigint not null,
  amount_min bigint not null,
  amount_max bigint not null,
  run_id text not null,
  primary key (worker, day, category)
);

create table if not exists backfill_ledger (
  id bigserial primary key,
  worker text not null,
  run_id text not null,
  idx int not null,
  day date not null,
  pod text not null,
  attempt int not null,
  status text not null check (status in ('ok', 'transient', 'fatal')),
  rows_read bigint not null,
  started_at timestamptz not null,
  finished_at timestamptz not null
);

create unique index if not exists one_ok_per_index on backfill_ledger (run_id, idx) where status = 'ok';

create or replace view ground_truth as
select (ts at time zone 'UTC')::date as day,
       category,
       count(*) as event_count,
       sum(amount_cents) as amount_total,
       min(amount_cents) as amount_min,
       max(amount_cents) as amount_max
from events
group by 1, 2;
