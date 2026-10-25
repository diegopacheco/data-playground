import time

import db
import diff
import embed
import lake


def sync(conn, table, label):
    started = time.perf_counter()
    table.refresh()
    last = db.watermark(conn)
    current = table.current_snapshot().snapshot_id
    rows_before, calls_before = embed.STATS["rows"], embed.STATS["model_calls"]
    change = diff.between(table, last, current)
    upserts = change["inserted"] + change["updated"]
    vectors = embed.embed_passages([row["text"] for row in upserts])
    with conn.transaction():
        for row, vector in zip(upserts, vectors):
            conn.execute(db.UPSERT, (row["id"], row["category"], row["text"], current, embed.to_pg(vector)))
        conn.execute("DELETE FROM documents WHERE id = ANY(%s)", (change["deleted"],))
        db.set_watermark(conn, current)
        payload = {
            "round": len(db.rounds(conn)) + 1,
            "label": label,
            "from_snapshot": str(last) if last is not None else None,
            "to_snapshot": str(current),
            "technique": change["technique"],
            "operations": change["operations"],
            "table_rows": lake.table_rows(table, current),
            "inserted": [row["id"] for row in change["inserted"]],
            "updated": [row["id"] for row in change["updated"]],
            "deleted": change["deleted"],
            "carried_over": change["carried_over"],
            "files_read": change["files_read"],
            "rows_read": change["rows_read"],
            "rows_embedded": embed.STATS["rows"] - rows_before,
            "model_calls": embed.STATS["model_calls"] - calls_before,
            "vectors_after": db.vector_count(conn),
            "seconds": round(time.perf_counter() - started, 3),
        }
        db.save_round(conn, payload)
    return payload
