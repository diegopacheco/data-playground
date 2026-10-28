import os
from contextlib import contextmanager

import psycopg
from psycopg import sql

DSN = os.environ.get("PG_DSN", "postgresql://backfill:backfill@r13-postgres:5432/backfill")

SCHEMA = """
DROP SCHEMA IF EXISTS public CASCADE;
CREATE SCHEMA public;
CREATE TABLE offsets (consumer text PRIMARY KEY, next_offset bigint NOT NULL);
CREATE TABLE lambda_config (id int PRIMARY KEY, batch_logic text NOT NULL, speed_logic text NOT NULL, watermark bigint NOT NULL);
CREATE TABLE lambda_master (event_id text PRIMARY KEY, log_offset bigint NOT NULL, day date NOT NULL, ts timestamptz NOT NULL, store text NOT NULL, kind text NOT NULL, amount_cents bigint NOT NULL);
CREATE TABLE lambda_batch_view (day date, store text, sales bigint NOT NULL, refunds bigint NOT NULL, revenue_cents bigint NOT NULL, PRIMARY KEY (day, store));
CREATE TABLE lambda_speed_view (day date, store text, sales bigint NOT NULL, refunds bigint NOT NULL, revenue_cents bigint NOT NULL, PRIMARY KEY (day, store));
CREATE TABLE lambda_speed_seen (event_id text PRIMARY KEY);
CREATE VIEW lambda_serving AS
  SELECT day, store, sum(sales)::bigint AS sales, sum(refunds)::bigint AS refunds, sum(revenue_cents)::bigint AS revenue_cents
  FROM (SELECT day, store, sales, refunds, revenue_cents FROM lambda_batch_view
        UNION ALL
        SELECT day, store, sales, refunds, revenue_cents FROM lambda_speed_view) merged
  GROUP BY day, store;
CREATE TABLE kappa_jobs (version text PRIMARY KEY, logic text NOT NULL, next_offset bigint NOT NULL, status text NOT NULL, events_read bigint NOT NULL);
CREATE TABLE kappa_state (id int PRIMARY KEY, active text);
INSERT INTO offsets VALUES ('lambda_master', 0), ('lambda_speed', 0);
INSERT INTO lambda_config VALUES (1, 'v1', 'v1', 0);
INSERT INTO kappa_state VALUES (1, NULL);
"""


@contextmanager
def tx():
    with psycopg.connect(DSN) as conn:
        with conn.cursor() as cur:
            yield cur


def get_offset(cur, name):
    cur.execute("SELECT next_offset FROM offsets WHERE consumer = %s", [name])
    return cur.fetchone()[0]


def set_offset(cur, name, value):
    cur.execute("UPDATE offsets SET next_offset = %s WHERE consumer = %s", [value, name])


def where_days(days):
    if days is None:
        return sql.SQL(""), []
    return sql.SQL(" WHERE day = ANY(%s::date[])"), [list(days)]


def rows(cur, relation, days=None):
    cond, params = where_days(days)
    cur.execute(sql.SQL("SELECT day::text, store, sales, refunds, revenue_cents FROM {}").format(sql.Identifier(relation)) + cond + sql.SQL(" ORDER BY day, store"), params)
    return [list(r) for r in cur.fetchall()]


def checksum(cur, relation, days=None):
    cond, params = where_days(days)
    q = sql.SQL("SELECT md5(coalesce(string_agg(concat_ws('|', day, store, sales, refunds, revenue_cents), ',' ORDER BY day, store), '')), count(*) FROM {}").format(sql.Identifier(relation))
    cur.execute(q + cond, params)
    digest, count = cur.fetchone()
    return {"md5": digest, "rows": count}
