import store

GROUP = "s3-dedup"


def apply(con, events):
    with con.transaction():
        for e in events:
            fresh = con.execute(
                "INSERT INTO processed_events VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING",
                (e["id"], e["topic"], e["key"], e["type"]),
            ).rowcount
            con.execute(
                """INSERT INTO projection VALUES (%s, %s, %s, 1) ON CONFLICT (aggregateid) DO UPDATE SET
                last_type = CASE WHEN excluded.applied = 1 THEN excluded.last_type ELSE projection.last_type END,
                applied = projection.applied + excluded.applied,
                deliveries = projection.deliveries + 1""",
                (e["key"], e["type"], fresh),
            )


def consume(con):
    return len(store.read(store.OUTBOX_TOPICS, group=GROUP, resume=True, then=lambda events: apply(con, events)))
