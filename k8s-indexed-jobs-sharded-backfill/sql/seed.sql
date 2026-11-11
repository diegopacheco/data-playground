do $$
declare
  start_day constant date := '2026-10-01';
  days constant int := 12;
  rows_per_day constant int := 250000;
  d date;
begin
  if exists (select 1 from pg_class where relname = 'events_' || to_char(start_day, 'YYYYMMDD')) then
    return;
  end if;
  for i in 0 .. days - 1 loop
    d := start_day + i;
    execute format(
      'create table events_%s partition of events for values from (%L) to (%L)',
      to_char(d, 'YYYYMMDD'), d::text || ' 00:00:00+00', (d + 1)::text || ' 00:00:00+00');
  end loop;
  insert into events (id, ts, category, amount_cents)
  select g,
         (start_day::timestamp at time zone 'UTC') + (g / rows_per_day) * interval '1 day' + ((g * 37) % 86400) * interval '1 second',
         (array['books', 'games', 'music', 'sports', 'tools'])[1 + (g * 13 + g / 7) % 5],
         1 + (g * 7919) % 50000
  from generate_series(0::bigint, days::bigint * rows_per_day - 1) as g;
  create index on events (ts);
  analyze events;
end
$$;
