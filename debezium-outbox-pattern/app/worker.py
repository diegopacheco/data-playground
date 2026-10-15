import json
import os
import signal
import sys
import uuid
from confluent_kafka import Producer
import service
import store

PREFIX = {"outbox": "K", "db-first": "D", "kafka-first": "F"}


def crash():
    os.kill(os.getpid(), signal.SIGKILL)


def insert(con, variant, order_id, amount):
    con.execute("INSERT INTO dual_write_orders VALUES (%s, %s, %s)", (variant, order_id, amount))


def publish(producer, variant, order_id, amount):
    producer.produce(
        f"{store.DUAL_TOPICS}{variant}.order",
        key=order_id,
        value=json.dumps({"order_id": order_id, "amount": amount, "version": 1}),
        headers={"id": str(uuid.uuid4()), "eventType": service.LIFECYCLE[0]},
    )
    if producer.flush(10):
        raise RuntimeError("kafka publish not acknowledged")


def run(variant, first, last, crash_at):
    con = store.db()
    producer = Producer({"bootstrap.servers": store.KAFKA, "acks": "all"})
    for n in range(first, last + 1):
        order_id = f"{PREFIX[variant]}-{n:04d}"
        amount = 10 + n
        if variant == "outbox":
            with con.transaction():
                service.place_order(con, order_id, "U-0001", amount)
                if n == crash_at:
                    crash()
        elif variant == "db-first":
            insert(con, variant, order_id, amount)
            if n == crash_at:
                crash()
            publish(producer, variant, order_id, amount)
        else:
            publish(producer, variant, order_id, amount)
            if n == crash_at:
                crash()
            insert(con, variant, order_id, amount)


if __name__ == "__main__":
    run(sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]))
