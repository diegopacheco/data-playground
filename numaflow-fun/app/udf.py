import json
import signal
import sys

from pynumaflow.mapper import Datum, MapServer, Message, Messages
from pynumaflow.sinker import Datum as SinkDatum, Response, Responses, SinkServer

from orders import process


def map_handler(keys: list[str], datum: Datum) -> Messages:
    order = process(datum.value)
    if order is None:
        print(json.dumps({"dropped": datum.value.decode(errors="replace")}), flush=True)
        return Messages(Message.to_drop())
    body = json.dumps(order).encode()
    return Messages(Message(body, keys=[order["id"]], tags=[order["tier"]]))


def sink_handler(datums) -> Responses:
    responses = Responses()
    for d in datums:
        print(json.dumps({"sink": json.loads(d.value)}), flush=True)
        responses.append(Response.as_success(d.id))
    return responses


def main(role):
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    if role == "map":
        MapServer(map_handler).start()
    elif role == "sink":
        SinkServer(sink_handler).start()
    else:
        sys.exit(f"unknown role {role}")


if __name__ == "__main__":
    main(sys.argv[1])
