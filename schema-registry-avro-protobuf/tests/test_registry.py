import io
import json
import os
import struct
import tempfile
import unittest
import urllib.error
import urllib.request

import fastavro
from confluent_kafka import Consumer, TopicPartition
from google.protobuf import descriptor_pb2, descriptor_pool, message_factory, unknown_fields
from grpc_tools import protoc

APP = os.environ.get("APP_URL", "http://localhost:8080")
REGISTRY = os.environ.get("REGISTRY_URL", "http://r10-registry:8080") + "/apis/registry/v3"
KAFKA = os.environ.get("KAFKA_BOOTSTRAP", "r10-kafka:9092")
ROOT = os.path.join(os.path.dirname(__file__), "..")
GROUP = "r10-tests"
MODES = ["BACKWARD", "FORWARD", "FULL", "NONE"]
TYPES = {"avro": ("AVRO", "application/json"), "protobuf": ("PROTOBUF", "application/x-protobuf")}
SAMPLES = {"long": 9007199254740993, "int": 7, "double": 12.5, "string": "text"}
PROTO_SAMPLES = {1: 12.5, 3: 9007199254740993, 5: 7, 9: "text"}


def http(method, url, body=None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as res:
            text = res.read().decode()
            return res.status, json.loads(text) if text.startswith(("{", "[")) else text
    except urllib.error.HTTPError as e:
        text = e.read().decode()
        e.close()
        return e.code, json.loads(text) if text.startswith("{") else text


def read(name):
    with open(os.path.join(ROOT, "schemas", name)) as f:
        return f.read()


CATALOG = json.loads(read("changes.json"))
with open(os.path.join(ROOT, "data", "orders.json")) as f:
    ORDERS = json.load(f)


def avro_can_read(writer_text, reader_text):
    writer = fastavro.parse_schema(json.loads(writer_text))
    reader = fastavro.parse_schema(json.loads(reader_text))
    record = {f["name"]: SAMPLES[f["type"]] for f in json.loads(writer_text)["fields"]}
    buf = io.BytesIO()
    fastavro.schemaless_writer(buf, writer, record)
    try:
        fastavro.schemaless_reader(io.BytesIO(buf.getvalue()), writer, reader)
        return True
    except Exception:
        return False


def compile_proto(text):
    with tempfile.TemporaryDirectory() as tmp:
        with open(os.path.join(tmp, "t.proto"), "w") as f:
            f.write(text)
        assert protoc.main(["protoc", f"-I{tmp}", f"--descriptor_set_out={tmp}/t.desc", f"{tmp}/t.proto"]) == 0
        fds = descriptor_pb2.FileDescriptorSet()
        with open(f"{tmp}/t.desc", "rb") as f:
            fds.ParseFromString(f.read())
    pool = descriptor_pool.DescriptorPool()
    pool.Add(fds.file[0])
    return message_factory.GetMessageClass(pool.FindMessageTypeByName("poc.Order"))


def proto_keeps_data(writer_text, reader_text):
    writer, reader = compile_proto(writer_text), compile_proto(reader_text)
    sent = writer()
    for field in writer.DESCRIPTOR.fields:
        setattr(sent, field.name, PROTO_SAMPLES[field.type])
    got = reader()
    got.ParseFromString(sent.SerializeToString())
    shared = [f.name for f in reader.DESCRIPTOR.fields if f.name in writer.DESCRIPTOR.fields_by_name]
    return all(getattr(got, name) == getattr(sent, name) for name in shared)


def registry_verdict(fmt, mode, schema):
    code, body = http("POST", f"{REGISTRY}/groups/{GROUP}/artifacts/{fmt}-{mode.lower()}/versions?dryRun=true",
                      {"content": {"content": schema, "contentType": TYPES[fmt][1]}})
    if code == 200:
        return True
    assert body.get("name") == "RuleViolationException", body
    return False


def read_topic(topic, start, end):
    consumer = Consumer({"bootstrap.servers": KAFKA, "group.id": "r10-tests", "enable.auto.commit": False})
    consumer.assign([TopicPartition(topic, 0, start)])
    out = []
    try:
        for _ in range(60):
            if len(out) >= end - start:
                break
            msg = consumer.poll(1.0)
            if msg is not None and not msg.error():
                magic, global_id = struct.unpack(">bI", msg.value()[:5])
                out.append((magic, global_id, msg.value()[5:]))
    finally:
        consumer.close()
    return out


def v1_view_avro(order):
    return {k: order[k] for k in ("id", "amount", "currency", "quantity", "note")}


class RegistryTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        code, _ = http("POST", f"{APP}/api/run")
        assert code == 200, "POST /api/run failed"
        cls.matrix = http("GET", f"{APP}/api/matrix")[1]
        cls.flow = http("GET", f"{APP}/api/flow")[1]
        http("DELETE", f"{REGISTRY}/groups/{GROUP}")
        for fmt, (artifact_type, content_type) in TYPES.items():
            base = read(CATALOG[fmt]["base"])
            for mode in MODES:
                code, body = http("POST", f"{REGISTRY}/groups/{GROUP}/artifacts", {
                    "artifactId": f"{fmt}-{mode.lower()}", "artifactType": artifact_type,
                    "firstVersion": {"content": {"content": base, "contentType": content_type}}})
                assert code == 200, body
                code, body = http("POST", f"{REGISTRY}/groups/{GROUP}/artifacts/{fmt}-{mode.lower()}/rules", {"ruleType": "COMPATIBILITY", "config": mode})
                assert code == 204, body
        cls.direct = {fmt: {c["id"]: {m: registry_verdict(fmt, m, read(c["file"])) for m in MODES} for c in CATALOG[fmt]["changes"]} for fmt in TYPES}

    @classmethod
    def tearDownClass(cls):
        http("DELETE", f"{REGISTRY}/groups/{GROUP}")

    def test_avro_verdict_in_every_mode_equals_what_a_real_avro_reader_can_decode(self):
        base = read(CATALOG["avro"]["base"])
        for change in CATALOG["avro"]["changes"]:
            new = read(change["file"])
            backward, forward = avro_can_read(base, new), avro_can_read(new, base)
            expected = {"BACKWARD": backward, "FORWARD": forward, "FULL": backward and forward, "NONE": True}
            self.assertEqual(self.direct["avro"][change["id"]], expected, change["id"])

    def test_avro_matrix_has_accepted_and_rejected_cells_in_every_checked_mode(self):
        for mode in ("BACKWARD", "FORWARD", "FULL"):
            verdicts = [v[mode] for v in self.direct["avro"].values()]
            self.assertIn(True, verdicts, mode)
            self.assertIn(False, verdicts, mode)

    def test_protobuf_accepted_change_never_loses_data_in_the_checked_direction(self):
        base = read(CATALOG["protobuf"]["base"])
        for change in CATALOG["protobuf"]["changes"]:
            new = read(change["file"])
            verdict = self.direct["protobuf"][change["id"]]
            if verdict["BACKWARD"]:
                self.assertTrue(proto_keeps_data(base, new), change["id"])
            if verdict["FORWARD"]:
                self.assertTrue(proto_keeps_data(new, base), change["id"])
            if verdict["FULL"]:
                self.assertTrue(proto_keeps_data(base, new) and proto_keeps_data(new, base), change["id"])

    def test_protobuf_changes_that_corrupt_data_are_rejected_by_every_checked_mode(self):
        base = read(CATALOG["protobuf"]["base"])
        corrupting = [c["id"] for c in CATALOG["protobuf"]["changes"] if not proto_keeps_data(base, read(c["file"])) and not proto_keeps_data(read(c["file"]), base)]
        self.assertEqual(sorted(corrupting), ["change_field_number", "change_field_type"])
        for change_id in corrupting:
            self.assertEqual(self.direct["protobuf"][change_id], {"BACKWARD": False, "FORWARD": False, "FULL": False, "NONE": True}, change_id)

    def test_protobuf_backward_removal_is_accepted_only_when_the_tag_and_name_are_reserved(self):
        base = read(CATALOG["protobuf"]["base"])
        self.assertTrue(proto_keeps_data(base, read("proto/remove_field.proto")))
        self.assertFalse(self.direct["protobuf"]["remove_field"]["BACKWARD"])
        self.assertTrue(self.direct["protobuf"]["remove_field_reserved"]["BACKWARD"])

    def test_none_mode_accepts_every_change_even_the_corrupting_ones(self):
        for fmt in TYPES:
            for change_id, verdict in self.direct[fmt].items():
                self.assertTrue(verdict["NONE"], f"{fmt} {change_id}")

    def test_full_accepts_only_what_both_backward_and_forward_accept(self):
        for fmt in TYPES:
            for change_id, v in self.direct[fmt].items():
                if v["FULL"]:
                    self.assertTrue(v["BACKWARD"] and v["FORWARD"], f"{fmt} {change_id}")

    def test_dry_run_checks_never_register_a_version(self):
        for fmt in TYPES:
            for mode in MODES:
                code, body = http("GET", f"{REGISTRY}/groups/{GROUP}/artifacts/{fmt}-{mode.lower()}/versions")
                self.assertEqual(body["count"], 1, f"{fmt} {mode}")

    def test_app_matrix_shows_the_same_verdicts_as_the_registry(self):
        for fmt in TYPES:
            for row in self.matrix[fmt]["changes"]:
                shown = {m: r["accepted"] for m, r in row["results"].items()}
                self.assertEqual(shown, self.direct[fmt][row["id"]], f"{fmt} {row['id']}")
                for mode, r in row["results"].items():
                    self.assertEqual(bool(r["causes"]), not r["accepted"], f"{fmt} {row['id']} {mode} must explain every rejection")

    def test_breaking_v3_is_rejected_and_the_registry_keeps_only_two_versions(self):
        for fmt, f in self.flow.items():
            v3 = [a for a in f["attempts"] if a["version"] == "v3"][0]
            self.assertFalse(v3["accepted"], fmt)
            self.assertTrue(v3["causes"], fmt)
            self.assertEqual(f["blocked_producers"], ["v3"], fmt)
            code, body = http("GET", f"{REGISTRY}/groups/{f['group']}/artifacts/{f['artifact']}/versions")
            self.assertEqual([v["version"] for v in body["versions"]], ["1", "2"], fmt)
            code, rule = http("GET", f"{REGISTRY}/groups/{f['group']}/artifacts/{f['artifact']}/rules/COMPATIBILITY")
            self.assertEqual(rule["config"], f["mode"], fmt)

    def test_topic_holds_every_order_framed_with_the_global_id_of_its_producer_version(self):
        for fmt, f in self.flow.items():
            ids = {a["version"]: a["global_id"] for a in f["attempts"] if a["accepted"]}
            raw = read_topic(f["topic"], f["start_offset"], f["end_offset"])
            self.assertEqual(len(raw), len(ORDERS["v1"]) + len(ORDERS["v2"]), fmt)
            self.assertTrue(all(magic == 0 for magic, _, _ in raw), fmt)
            self.assertEqual(sorted(g for _, g, _ in raw), sorted([ids["v1"]] * len(ORDERS["v1"]) + [ids["v2"]] * len(ORDERS["v2"])), fmt)

    def test_avro_messages_decode_independently_to_the_input_orders(self):
        f = self.flow["avro"]
        v2_reader = fastavro.parse_schema(json.loads(read(CATALOG["flow"]["avro"]["v2"])))
        decoded = {}
        for _, global_id, payload in read_topic(f["topic"], f["start_offset"], f["end_offset"]):
            code, writer_text = http("GET", f"{REGISTRY}/ids/globalIds/{global_id}")
            writer = fastavro.parse_schema(writer_text if isinstance(writer_text, dict) else json.loads(writer_text))
            record = fastavro.schemaless_reader(io.BytesIO(payload), writer, v2_reader)
            decoded[record["id"]] = record
        expected = {o["id"]: {**o, "status": "NEW"} for o in ORDERS["v1"]}
        expected.update({o["id"]: o for o in ORDERS["v2"]})
        self.assertEqual(decoded, expected)

    def test_avro_v1_consumer_reads_v2_orders_without_status(self):
        rows = {m["key"]: m for m in self.flow["avro"]["messages"]}
        for order in ORDERS["v2"]:
            got = rows[str(order["id"])]["readers"]["consumer v1"]
            self.assertTrue(got["ok"])
            self.assertEqual(got["record"], v1_view_avro(order))
            self.assertEqual(rows[str(order["id"])]["writer"], "v2")

    def test_avro_v2_consumer_reads_v1_orders_with_status_defaulted_to_new(self):
        rows = {m["key"]: m for m in self.flow["avro"]["messages"]}
        for order in ORDERS["v1"]:
            got = rows[str(order["id"])]["readers"]["consumer v2"]
            self.assertTrue(got["ok"])
            self.assertEqual(got["record"], {**order, "status": "NEW"})
            self.assertEqual(rows[str(order["id"])]["writer"], "v1")

    def test_protobuf_v1_consumer_reads_v2_orders_and_keeps_status_as_unknown_tag_5(self):
        rows = {m["key"]: m for m in self.flow["protobuf"]["messages"]}
        for order in ORDERS["v2"]:
            got = rows[str(order["id"])]["readers"]["consumer v1"]
            self.assertEqual(got["record"], {k: order[k] for k in ("id", "amount", "currency", "quantity")})
            self.assertEqual(got["unknown_fields"], [5])

    def test_protobuf_v2_consumer_reads_v1_orders_with_empty_status(self):
        rows = {m["key"]: m for m in self.flow["protobuf"]["messages"]}
        for order in ORDERS["v1"]:
            got = rows[str(order["id"])]["readers"]["consumer v2"]
            self.assertEqual(got["record"], {**{k: order[k] for k in ("id", "amount", "currency", "quantity")}, "status": ""})
            self.assertEqual(got["unknown_fields"], [])

    def test_protobuf_messages_decode_independently_to_the_input_orders(self):
        f = self.flow["protobuf"]
        v2 = compile_proto(read(CATALOG["flow"]["protobuf"]["v2"]))
        decoded = {}
        for _, _, payload in read_topic(f["topic"], f["start_offset"], f["end_offset"]):
            msg = v2()
            msg.ParseFromString(payload)
            self.assertEqual(len(unknown_fields.UnknownFieldSet(msg)), 0)
            decoded[msg.id] = {"id": msg.id, "amount": msg.amount, "currency": msg.currency, "quantity": msg.quantity, "status": msg.status}
        expected = {o["id"]: {"id": o["id"], "amount": o["amount"], "currency": o["currency"], "quantity": o["quantity"], "status": o.get("status", "")} for o in ORDERS["v1"] + ORDERS["v2"]}
        self.assertEqual(decoded, expected)

    def test_check_endpoint_rejects_a_breaking_change_and_accepts_a_safe_one(self):
        code, bad = http("POST", f"{APP}/api/check", {"format": "avro", "mode": "BACKWARD", "schema": read("avro/change_field_type.avsc")})
        self.assertEqual((code, bad["accepted"]), (200, False))
        code, good = http("POST", f"{APP}/api/check", {"format": "avro", "mode": "BACKWARD", "schema": read("avro/add_optional_field.avsc")})
        self.assertEqual((code, good["accepted"]), (200, True))

    def test_ui_page_has_every_tab(self):
        code, html = http("GET", f"{APP}/")
        self.assertEqual(code, 200)
        for tab in ("Compatibility", "Producers and consumers", "Registry"):
            self.assertIn(tab, html)
