import json
import os

from bytewax import operators as op
from bytewax.connectors.kafka import KafkaSinkMessage
from bytewax.connectors.kafka import operators as kop
from bytewax.dataflow import Dataflow

from core import aggregate
from store import SqliteSink

BROKERS = [os.environ.get("KAFKA_BROKERS", "localhost:22892")]
IN_TOPIC = os.environ.get("IN_TOPIC", "orders")
OUT_TOPIC = os.environ.get("OUT_TOPIC", "order-aggregates")
STORE_DB = os.environ.get("STORE_DB", "state/store.db")


def to_message(record):
    return KafkaSinkMessage(record["category"].encode(), json.dumps(record).encode())


flow = Dataflow("orders_by_category")
source = kop.input("orders_in", flow, brokers=BROKERS, topics=[IN_TOPIC])
op.inspect("source_errors", source.errs, lambda step, err: print(step, err, flush=True))
results = aggregate(op.map("decode", source.oks, lambda m: m.value.decode()))
kop.output("aggregates_out", op.map("to_message", results, to_message), brokers=BROKERS, topic=OUT_TOPIC)
op.output("store_out", results, SqliteSink(STORE_DB))
