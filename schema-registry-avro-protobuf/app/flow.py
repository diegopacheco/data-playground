import json
import os
import time

from confluent_kafka import Consumer, Producer, TopicPartition
from confluent_kafka.admin import AdminClient, NewTopic

import matrix
import registry
import serdes

BOOTSTRAP = os.environ.get("KAFKA_BOOTSTRAP", "localhost:27502")
DATA = os.environ.get("DATA_DIR", os.path.join(os.path.dirname(__file__), "..", "data"))
GROUP = "r10-flow"


def orders():
    with open(os.path.join(DATA, "orders.json")) as f:
        return json.load(f)


def ensure_topic(topic):
    admin = AdminClient({"bootstrap.servers": BOOTSTRAP})
    if topic in admin.list_topics(timeout=20).topics:
        return
    for future in admin.create_topics([NewTopic(topic, num_partitions=1, replication_factor=1)]).values():
        future.result(20)


def end_offset(topic):
    consumer = Consumer({"bootstrap.servers": BOOTSTRAP, "group.id": "r10-watermarks"})
    try:
        return consumer.get_watermark_offsets(TopicPartition(topic, 0), timeout=20)[1]
    finally:
        consumer.close()


def register(fmt, spec):
    artifact = spec["topic"] + "-value"
    artifact_type = matrix.TYPES[fmt]
    first = registry.create_artifact(GROUP, artifact, artifact_type, matrix.read(spec["v1"]), spec["mode"])
    second = registry.add_version(GROUP, artifact, artifact_type, matrix.read(spec["v2"]))
    attempts = [{"version": "v1", "file": spec["v1"], "accepted": True, "registry_version": first["version"], "global_id": first["globalId"], "causes": []},
                {"version": "v2", "file": spec["v2"], "accepted": True, "registry_version": second["version"], "global_id": second["globalId"], "causes": []}]
    try:
        third = registry.add_version(GROUP, artifact, artifact_type, matrix.read(spec["v3"]))
        attempts.append({"version": "v3", "file": spec["v3"], "accepted": True, "registry_version": third["version"], "global_id": third["globalId"], "causes": []})
    except registry.RuleViolation as v:
        attempts.append({"version": "v3", "file": spec["v3"], "accepted": False, "registry_version": None, "global_id": None, "causes": v.causes})
    return artifact, attempts


def encoder(fmt, text):
    if fmt == "avro":
        schema = serdes.avro_schema(text)
        fields = serdes.avro_fields(text)
        return lambda record: serdes.avro_encode(schema, {k: record[k] for k in fields})
    cls = serdes.proto_class(text)
    return lambda record: serdes.proto_encode(cls, record)


def decoder(fmt, text):
    if fmt == "avro":
        reader = serdes.avro_schema(text)
        writers = {}

        def decode(global_id, payload):
            if global_id not in writers:
                writers[global_id] = serdes.avro_schema(registry.schema_by_global_id(global_id))
            return serdes.avro_decode(payload, writers[global_id], reader), []
        return decode
    cls = serdes.proto_class(text)
    return lambda global_id, payload: serdes.proto_decode(cls, payload)


def produce(fmt, spec, attempts):
    data = orders()
    producer = Producer({"bootstrap.servers": BOOTSTRAP, "acks": "all"})
    produced = []
    writers = {a["version"]: (a["global_id"], encoder(fmt, matrix.read(a["file"]))) for a in attempts if a["accepted"]}
    batches = [("v1", data["v1"]), ("v2", data["v2"])]
    for i in range(max(len(b) for _, b in batches)):
        for version, batch in batches:
            if i < len(batch):
                global_id, encode = writers[version]
                producer.produce(spec["topic"], key=str(batch[i]["id"]).encode(), value=serdes.frame(global_id, encode(batch[i])))
                produced.append({"producer": version, "id": batch[i]["id"], "global_id": global_id})
    blocked = [a["version"] for a in attempts if not a["accepted"]]
    if producer.flush(30) != 0:
        raise RuntimeError("producer could not deliver every message")
    return produced, blocked


def consume(topic, start, end, decoders, versions):
    consumer = Consumer({"bootstrap.servers": BOOTSTRAP, "group.id": f"r10-readers-{topic}", "enable.auto.commit": False})
    consumer.assign([TopicPartition(topic, 0, start)])
    rows = []
    deadline = time.time() + 30
    try:
        while len(rows) < end - start and time.time() < deadline:
            msg = consumer.poll(1.0)
            if msg is None:
                continue
            if msg.error():
                raise RuntimeError(str(msg.error()))
            global_id, payload = serdes.unframe(msg.value())
            row = {"offset": msg.offset(), "key": msg.key().decode(), "global_id": global_id, "writer": versions.get(global_id), "bytes": len(payload), "readers": {}}
            for name, decode in decoders.items():
                try:
                    record, unknown = decode(global_id, payload)
                    row["readers"][name] = {"ok": True, "record": record, "unknown_fields": unknown}
                except Exception as e:
                    row["readers"][name] = {"ok": False, "error": str(e)}
            rows.append(row)
    finally:
        consumer.close()
    return rows


def run():
    registry.delete_group(GROUP)
    cat = matrix.catalog()
    out = {}
    for fmt, spec in cat["flow"].items():
        artifact, attempts = register(fmt, spec)
        ensure_topic(spec["topic"])
        start = end_offset(spec["topic"])
        produced, blocked = produce(fmt, spec, attempts)
        end = end_offset(spec["topic"])
        versions = {a["global_id"]: a["version"] for a in attempts if a["accepted"]}
        decoders = {f"consumer {v}": decoder(fmt, matrix.read(spec[v])) for v in ("v1", "v2")}
        messages = consume(spec["topic"], start, end, decoders, versions)
        out[fmt] = {"topic": spec["topic"], "artifact": artifact, "group": GROUP, "mode": spec["mode"], "attempts": attempts,
                    "produced": produced, "blocked_producers": blocked, "start_offset": start, "end_offset": end,
                    "schemas": {v: matrix.read(spec[v]) for v in ("v1", "v2", "v3")}, "messages": messages}
    return out
