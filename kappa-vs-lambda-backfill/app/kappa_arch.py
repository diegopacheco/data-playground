import re
import time

from psycopg import sql

import db
import eventlog
import rules
import stream

VERSION = re.compile(r"^v[0-9]{1,4}$")


def daily(version):
    return f"kappa_daily_{version}"


def seen(version):
    return f"kappa_seen_{version}"


def validate(version, logic="v1"):
    if not VERSION.match(version or "") or logic not in rules.RULES:
        raise ValueError("version must look like v2 and logic must be v1 or v2")


def active(cur):
    cur.execute("SELECT s.active, j.logic, j.next_offset FROM kappa_state s LEFT JOIN kappa_jobs j ON j.version = s.active WHERE s.id = 1")
    version, logic, next_offset = cur.fetchone()
    return {"version": version, "logic": logic, "next_offset": next_offset}


def jobs(cur):
    cur.execute("SELECT version, logic, next_offset, status, events_read FROM kappa_jobs ORDER BY length(version), version")
    return [dict(zip(["version", "logic", "next_offset", "status", "events_read"], r)) for r in cur.fetchall()]


def create_job(version, logic):
    validate(version, logic)
    with db.tx() as cur:
        if active(cur)["version"] == version:
            raise ValueError(f"{version} is serving, replay into a new version and swap")
        cur.execute(sql.SQL("DROP TABLE IF EXISTS {}, {}").format(sql.Identifier(daily(version)), sql.Identifier(seen(version))))
        cur.execute(sql.SQL(
            "CREATE TABLE {} (day date, store text, sales bigint NOT NULL, refunds bigint NOT NULL, "
            "revenue_cents bigint NOT NULL, PRIMARY KEY (day, store))"
        ).format(sql.Identifier(daily(version))))
        cur.execute(sql.SQL("CREATE TABLE {} (event_id text PRIMARY KEY)").format(sql.Identifier(seen(version))))
        cur.execute(
            "INSERT INTO kappa_jobs VALUES (%s, %s, 0, 'running', 0) ON CONFLICT (version) DO UPDATE "
            "SET logic = EXCLUDED.logic, next_offset = 0, status = 'running', events_read = 0",
            [version, logic],
        )


def step(version, logic, start, end):
    events = eventlog.read(start, end)
    if not events:
        return 0
    with db.tx() as cur:
        applied = stream.apply(cur, events, logic, daily(version), seen(version))
        cur.execute("UPDATE kappa_jobs SET next_offset = %s, events_read = events_read + %s WHERE version = %s", [end, len(events), version])
    return applied


def run_jobs(end):
    with db.tx() as cur:
        running = [j for j in jobs(cur) if j["status"] == "running"]
    for j in running:
        step(j["version"], j["logic"], j["next_offset"], end)


def replay(version, logic):
    started = time.perf_counter()
    create_job(version, logic)
    end = eventlog.end_offset()
    step(version, logic, 0, end)
    with db.tx() as cur:
        result = {"version": version, "logic": logic, "events_replayed": end, "checksum": db.checksum(cur, daily(version)), "rows": db.rows(cur, daily(version))}
    result["ms"] = round((time.perf_counter() - started) * 1000, 1)
    return result


def swap(version):
    validate(version)
    with db.tx() as cur:
        cur.execute("UPDATE kappa_jobs SET status = 'running' WHERE version = %s RETURNING logic, next_offset", [version])
        job = cur.fetchone()
        if job is None:
            raise ValueError(f"no job {version}, replay it first")
    step(version, job[0], job[1], eventlog.end_offset())
    with db.tx() as cur:
        previous = active(cur)["version"]
        cur.execute(sql.SQL(
            "CREATE OR REPLACE VIEW kappa_serving AS SELECT day, store, sales, refunds, revenue_cents FROM {}"
        ).format(sql.Identifier(daily(version))))
        cur.execute("UPDATE kappa_state SET active = %s WHERE id = 1", [version])
        if previous and previous != version:
            cur.execute("UPDATE kappa_jobs SET status = 'retired' WHERE version = %s", [previous])
    return {"active": version, "previous": previous}


def backfill_day(day):
    started = time.perf_counter()
    with db.tx() as cur:
        job = active(cur)
    events = eventlog.read(0, job["next_offset"])
    firsts = [e for e in rules.first_seen(events) if e["ts"][:10] == day]
    rows = rules.to_rows(rules.aggregate(firsts, job["logic"]))
    table = sql.Identifier(daily(job["version"]))
    with db.tx() as cur:
        cur.execute(sql.SQL("DELETE FROM {} WHERE day = %s").format(table), [day])
        cur.executemany(sql.SQL("INSERT INTO {} (day, store, sales, refunds, revenue_cents) VALUES (%s, %s, %s, %s, %s)").format(table), rows)
        result = {
            "days": [day],
            "version": job["version"],
            "logic": job["logic"],
            "events_replayed": len(events),
            "events_for_day": len(firsts),
            "checksum": db.checksum(cur, daily(job["version"]), [day]),
            "rows": db.rows(cur, daily(job["version"]), [day]),
        }
    result["ms"] = round((time.perf_counter() - started) * 1000, 1)
    return result


def rewind():
    with db.tx() as cur:
        cur.execute("UPDATE kappa_jobs SET next_offset = 0 WHERE version = (SELECT active FROM kappa_state WHERE id = 1)")
