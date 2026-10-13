import events

DATABASE = "bench"
TABLES = {
    "base": "bench.events_base",
    "projection": "bench.events_proj",
    "view": "bench.events_mv",
}
PROJECTION = "daily_totals"
TARGET = "bench.daily_totals"
VIEW = "bench.daily_totals_mv"

CREATE_TABLES = [
    f"DROP DATABASE IF EXISTS {DATABASE} SYNC",
    f"CREATE DATABASE {DATABASE}",
    f"""
    CREATE TABLE {TABLES["base"]} (
        event_id UInt64,
        ts DateTime('UTC'),
        user_id UInt32,
        country LowCardinality(String),
        device LowCardinality(String),
        event_type LowCardinality(String),
        amount UInt32
    ) ENGINE = MergeTree ORDER BY (user_id, ts)
    """,
    f"CREATE TABLE {TABLES['projection']} AS {TABLES['base']}",
    f"CREATE TABLE {TABLES['view']} AS {TABLES['base']}",
]

ADD_PROJECTION = f"""
    ALTER TABLE {TABLES["projection"]} ADD PROJECTION {PROJECTION} (
        SELECT toDate(ts) AS day, country, device, count(), sum(amount), max(amount)
        GROUP BY day, country, device
    )
"""

CREATE_TARGET = f"""
    CREATE TABLE {TARGET} (
        day Date,
        country LowCardinality(String),
        device LowCardinality(String),
        events AggregateFunction(count),
        amount_sum AggregateFunction(sum, UInt32),
        amount_max AggregateFunction(max, UInt32)
    ) ENGINE = AggregatingMergeTree ORDER BY (day, country, device)
"""

VIEW_SELECT = f"""
    SELECT toDate(ts) AS day, country, device,
           countState() AS events, sumState(amount) AS amount_sum, maxState(amount) AS amount_max
    FROM {TABLES["view"]}
    {{where}}
    GROUP BY day, country, device
"""

CREATE_VIEW = f"CREATE MATERIALIZED VIEW {VIEW} TO {TARGET} AS {VIEW_SELECT.format(where='')}"

MATERIALIZE_PROJECTION = f"ALTER TABLE {TABLES['projection']} MATERIALIZE PROJECTION {PROJECTION}"
BACKFILL_VIEW = f"INSERT INTO {TARGET} {VIEW_SELECT.format(where=f'WHERE event_id < {events.HISTORIC_ROWS}')}"
REPAIR_VIEW = [f"TRUNCATE TABLE {TARGET}", f"INSERT INTO {TARGET} {VIEW_SELECT.format(where='')}"]

DELETE_WHERE = "country = 'BR' AND event_type = 'refund'"
UPDATE_SET = "amount = amount * 2 WHERE device = 'tablet' AND event_type = 'purchase'"
