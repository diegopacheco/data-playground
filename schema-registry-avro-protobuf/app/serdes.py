import io
import json
import os
import struct
import tempfile

import fastavro
from google.protobuf import descriptor_pb2, descriptor_pool, message_factory, unknown_fields
from grpc_tools import protoc

MAGIC = 0


def frame(global_id, payload):
    return struct.pack(">bI", MAGIC, global_id) + payload


def unframe(data):
    magic, global_id = struct.unpack(">bI", data[:5])
    if magic != MAGIC:
        raise ValueError(f"unknown magic byte {magic}")
    return global_id, data[5:]


def avro_schema(text):
    return fastavro.parse_schema(json.loads(text))


def avro_encode(schema, record):
    out = io.BytesIO()
    fastavro.schemaless_writer(out, schema, record)
    return out.getvalue()


def avro_decode(payload, writer, reader):
    return fastavro.schemaless_reader(io.BytesIO(payload), writer, reader)


def avro_fields(text):
    return [f["name"] for f in json.loads(text)["fields"]]


def proto_class(text):
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, "order.proto")
        out = os.path.join(tmp, "order.desc")
        with open(src, "w") as f:
            f.write(text)
        code = protoc.main(["protoc", f"-I{tmp}", f"--descriptor_set_out={out}", src])
        if code != 0:
            raise ValueError("protoc could not compile the schema")
        files = descriptor_pb2.FileDescriptorSet()
        with open(out, "rb") as f:
            files.ParseFromString(f.read())
    pool = descriptor_pool.DescriptorPool()
    for fd in files.file:
        pool.Add(fd)
    return message_factory.GetMessageClass(pool.FindMessageTypeByName("poc.Order"))


def proto_fields(cls):
    return [f.name for f in cls.DESCRIPTOR.fields]


def proto_encode(cls, record):
    msg = cls()
    for name in proto_fields(cls):
        if name in record:
            setattr(msg, name, record[name])
    return msg.SerializeToString()


def proto_decode(cls, payload):
    msg = cls()
    msg.ParseFromString(payload)
    out = {name: getattr(msg, name) for name in proto_fields(cls)}
    unknown = sorted({f.field_number for f in unknown_fields.UnknownFieldSet(msg)})
    return out, unknown
