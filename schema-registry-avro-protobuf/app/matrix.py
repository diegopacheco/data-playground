import json
import os

import registry
import serdes

SCHEMAS = os.environ.get("SCHEMAS_DIR", os.path.join(os.path.dirname(__file__), "..", "schemas"))
GROUP = "r10-matrix"
TYPES = {"avro": "AVRO", "protobuf": "PROTOBUF"}
SAMPLES = {"long": 9007199254740993, "int": 7, "double": 12.5, "string": "value"}
PROTO_TYPES = {1: "double", 3: "long", 5: "int", 9: "string"}


def catalog():
    with open(os.path.join(SCHEMAS, "changes.json")) as f:
        return json.load(f)


def read(name):
    with open(os.path.join(SCHEMAS, name)) as f:
        return f.read()


def artifact_id(fmt, mode):
    return f"{fmt}-{mode.lower()}"


def avro_reads(writer_text, reader_text):
    record = {f["name"]: SAMPLES[f["type"]] for f in json.loads(writer_text)["fields"]}
    writer = serdes.avro_schema(writer_text)
    try:
        serdes.avro_decode(serdes.avro_encode(writer, record), writer, serdes.avro_schema(reader_text))
        return True
    except Exception:
        return False


def proto_reads(writer_text, reader_text):
    writer = serdes.proto_class(writer_text)
    reader = serdes.proto_class(reader_text)
    record = {f.name: SAMPLES[PROTO_TYPES[f.type]] for f in writer.DESCRIPTOR.fields}
    decoded, _ = serdes.proto_decode(reader, serdes.proto_encode(writer, record))
    return all(decoded[name] == record[name] for name in decoded if name in record)


def run():
    registry.delete_group(GROUP)
    cat = catalog()
    out = {"modes": cat["modes"]}
    for fmt, artifact_type in TYPES.items():
        base = read(cat[fmt]["base"])
        reads = avro_reads if fmt == "avro" else proto_reads
        for mode in cat["modes"]:
            registry.create_artifact(GROUP, artifact_id(fmt, mode), artifact_type, base, mode)
        rows = []
        for change in cat[fmt]["changes"]:
            schema = read(change["file"])
            results = {mode: registry.check(GROUP, artifact_id(fmt, mode), artifact_type, schema) for mode in cat["modes"]}
            rows.append({**change, "schema": schema, "results": results,
                         "new_reads_old": reads(base, schema), "old_reads_new": reads(schema, base)})
        out[fmt] = {"artifact_type": artifact_type, "base": base, "base_file": cat[fmt]["base"], "changes": rows}
    return out


def try_change(fmt, mode, schema):
    return registry.check(GROUP, artifact_id(fmt, mode), TYPES[fmt], schema)
