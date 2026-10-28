import time

import db
import eventlog
import rules
import stream

BATCH_SQL = {
    "v1": """INSERT INTO lambda_batch_view (day, store, sales, refunds, revenue_cents)
SELECT day, store,
       count(*) FILTER (WHERE kind = 'sale'),
       count(*) FILTER (WHERE kind = 'refund'),
       sum(amount_cents)
FROM lambda_master
WHERE log_offset < %(watermark)s AND day = ANY(%(days)s::date[])
GROUP BY day, store""",
    "v2": """INSERT INTO lambda_batch_view (day, store, sales, refunds, revenue_cents)
SELECT day, store,
       count(*) FILTER (WHERE kind = 'sale'),
       count(*) FILTER (WHERE kind = 'refund'),
       sum(CASE WHEN kind = 'refund' THEN -amount_cents ELSE amount_cents END)
FROM lambda_master
WHERE log_offset < %(watermark)s AND day = ANY(%(days)s::date[])
GROUP BY day, store""",
}


def config(cur):
    cur.execute("SELECT batch_logic, speed_logic, watermark FROM lambda_config WHERE id = 1")
    batch_logic, speed_logic, watermark = cur.fetchone()
    return {"batch_logic": batch_logic, "speed_logic": speed_logic, "watermark": watermark}


def ingest_master(end):
    with db.tx() as cur:
        events = eventlog.read(db.get_offset(cur, "lambda_master"), end)
        if not events:
            return 0
        cur.executemany(
            "INSERT INTO lambda_master VALUES (%s, %s, %s, %s, %s, %s, %s) ON CONFLICT (event_id) DO NOTHING",
            [(e["event_id"], off, e["ts"][:10], e["ts"], e["store"], e["kind"], e["amount_cents"]) for off, e in events],
        )
        db.set_offset(cur, "lambda_master", end)
        return len(events)


def speed(end):
    with db.tx() as cur:
        cfg = config(cur)
        events = eventlog.read(db.get_offset(cur, "lambda_speed"), end)
        if not events:
            return 0
        ids = list({e["event_id"] for _, e in events})
        cur.execute("SELECT event_id FROM lambda_master WHERE event_id = ANY(%s) AND log_offset < %s", [ids, cfg["watermark"]])
        covered = frozenset(r[0] for r in cur.fetchall())
        applied = stream.apply(cur, events, cfg["speed_logic"], "lambda_speed_view", "lambda_speed_seen", covered)
        db.set_offset(cur, "lambda_speed", end)
        return applied


def reset_speed(cur, watermark):
    cur.execute("TRUNCATE lambda_speed_view, lambda_speed_seen")
    db.set_offset(cur, "lambda_speed", watermark)


def batch(days=None, advance=False):
    started = time.perf_counter()
    with db.tx() as cur:
        cfg = config(cur)
        watermark = cfg["watermark"]
        if advance:
            days = None
            watermark = db.get_offset(cur, "lambda_master")
            cur.execute("UPDATE lambda_config SET watermark = %s WHERE id = 1", [watermark])
            reset_speed(cur, watermark)
        if days is None:
            cur.execute("SELECT DISTINCT day::text FROM lambda_master WHERE log_offset < %s ORDER BY 1", [watermark])
            days = [r[0] for r in cur.fetchall()]
        cur.execute("DELETE FROM lambda_batch_view WHERE day = ANY(%s::date[])", [days])
        cur.execute(BATCH_SQL[cfg["batch_logic"]], {"watermark": watermark, "days": days})
        cur.execute("SELECT count(*) FROM lambda_master WHERE log_offset < %s AND day = ANY(%s::date[])", [watermark, days])
        scanned = cur.fetchone()[0]
        result = {
            "days": days,
            "logic": cfg["batch_logic"],
            "watermark": watermark,
            "advanced": advance,
            "master_rows_scanned": scanned,
            "checksum": db.checksum(cur, "lambda_batch_view", days),
            "rows": db.rows(cur, "lambda_batch_view", days),
        }
    result["ms"] = round((time.perf_counter() - started) * 1000, 1)
    return result


def deploy(layer, logic):
    if layer not in ("batch", "speed") or logic not in rules.RULES:
        raise ValueError("layer must be batch or speed and logic v1 or v2")
    with db.tx() as cur:
        cur.execute(f"UPDATE lambda_config SET {layer}_logic = %s WHERE id = 1", [logic])
        if layer == "speed":
            reset_speed(cur, config(cur)["watermark"])
    return {"layer": layer, "logic": logic}


def rewind():
    with db.tx() as cur:
        cfg = config(cur)
        db.set_offset(cur, "lambda_master", 0)
        db.set_offset(cur, "lambda_speed", cfg["watermark"])
