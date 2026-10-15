import os
import psycopg
from confluent_kafka import Consumer, TopicPartition

PG_PORT = os.environ.get("PG_PORT", "30200")
KAFKA = "localhost:" + os.environ.get("KAFKA_PORT", "30201")
PG_DSN = f"host=localhost port={PG_PORT} dbname=shop user=s3 password=s3password"
OUTBOX_TOPICS = "outbox.event."
DUAL_TOPICS = "dualwrite."


def db():
    return psycopg.connect(PG_DSN, autocommit=True)


def rows(con, sql, params=None):
    cur = con.execute(sql, params)
    cols = [d.name for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def scalar(con, sql, params=None):
    return con.execute(sql, params).fetchone()[0]


def set_fact(con, name, value):
    con.execute("INSERT INTO facts VALUES (%s, %s) ON CONFLICT (name) DO UPDATE SET value = excluded.value", (name, value))


def facts(con):
    return {r["name"]: r["value"] for r in rows(con, "SELECT name, value FROM facts ORDER BY name")}


def event(message):
    headers = {k: v.decode() for k, v in message.headers() or []}
    return {
        "topic": message.topic(),
        "partition": message.partition(),
        "offset": message.offset(),
        "key": message.key().decode() if message.key() else None,
        "id": headers.get("id"),
        "type": headers.get("eventType"),
        "value": message.value().decode() if message.value() is not None else None,
    }


def read(prefix, group="s3-reader", resume=False, then=None):
    consumer = Consumer({"bootstrap.servers": KAFKA, "group.id": group, "enable.auto.commit": False})
    try:
        topics = consumer.list_topics(timeout=10).topics
        parts = [TopicPartition(t, p) for t in sorted(topics) if t.startswith(prefix) for p in topics[t].partitions]
        if resume and parts:
            parts = consumer.committed(parts, timeout=10)
        ends = {}
        for part in parts:
            low, high = consumer.get_watermark_offsets(part, timeout=10)
            part.offset = max(part.offset, low)
            if high > part.offset:
                ends[(part.topic, part.partition)] = high
        consumer.assign([p for p in parts if (p.topic, p.partition) in ends])
        todo = dict(ends)
        events = []
        idle = 0
        while todo and idle < 30:
            message = consumer.poll(1)
            if message is None:
                idle += 1
                continue
            if message.error():
                raise RuntimeError(str(message.error()))
            idle = 0
            where = (message.topic(), message.partition())
            if where not in todo:
                continue
            events.append(event(message))
            if message.offset() + 1 >= todo[where]:
                del todo[where]
        if todo:
            raise RuntimeError(f"kafka read incomplete, missing {todo}")
        events.sort(key=lambda e: (e["topic"], e["partition"], e["offset"]))
        if then:
            then(events)
        if resume and ends:
            consumer.commit(offsets=[TopicPartition(t, p, o) for (t, p), o in ends.items()], asynchronous=False)
        return events
    finally:
        consumer.close()
