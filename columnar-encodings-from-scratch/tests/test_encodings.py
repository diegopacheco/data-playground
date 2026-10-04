import json
import math
import os
import random
import struct
import time
import unittest
import urllib.error
import urllib.request

BASE = os.environ.get("UI_URL", "http://localhost:8080")
SLICE = 20000


def call(path, body=None):
    req = urllib.request.Request(BASE + path, data=body, method="POST" if body is not None else "GET")
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())


def wait_results():
    deadline = time.time() + 120
    while time.time() < deadline:
        try:
            return call("/api/results")
        except urllib.error.HTTPError as e:
            if e.code != 503:
                raise
        time.sleep(1)
    raise AssertionError("benchmark never finished")


def zigzag(v):
    return ((v << 1) ^ (v >> 63)) & 0xFFFFFFFFFFFFFFFF


def varint_len(u):
    return max(1, math.ceil(u.bit_length() / 7))


def packed(count, width):
    return (count * width + 7) // 8


def blocks(values, size):
    return [values[i:i + size] for i in range(0, len(values), size)]


def block_bytes(block):
    lo = min(block)
    return varint_len(zigzag(lo)) + 1 + packed(len(block), (max(block) - lo).bit_length())


def item_len(v):
    if isinstance(v, str):
        n = len(v.encode())
        return varint_len(n) + n
    return 8


def runs(values):
    out = []
    for v in values:
        if out and out[-1][1] == v:
            out[-1][0] += 1
        else:
            out.append([1, v])
    return out


def wrap(v):
    return ((v + 2 ** 63) % 2 ** 64) - 2 ** 63


def bits(v):
    return struct.unpack("<Q", struct.pack("<d", v))[0]


def expected_size(encoding, values):
    if values and isinstance(values[0], float):
        values = [bits(v) for v in values]
    n = len(values)
    head = varint_len(n)
    if encoding == "plain":
        return head + sum(item_len(v) for v in values)
    if encoding == "rle":
        return head + sum(varint_len(k) + item_len(v) for k, v in runs(values))
    if encoding == "dict":
        distinct = list(dict.fromkeys(values))
        return head + varint_len(len(distinct)) + sum(item_len(v) for v in distinct) + 1 + packed(n, (len(distinct) - 1).bit_length())
    if encoding == "bitpack":
        return head + 1 + packed(n, max(zigzag(v) for v in values).bit_length())
    if encoding == "for":
        return head + sum(block_bytes(b) for b in blocks(values, 1024))
    if encoding == "delta":
        deltas = [wrap(b - a) for a, b in zip(values, values[1:])]
        return head + varint_len(zigzag(values[0])) + sum(block_bytes(b) for b in blocks(deltas, 128))
    return None


def token(kind, v):
    if kind == "float":
        return "0x%016x" % bits(v)
    if kind == "str":
        return v.encode().hex()
    return str(v)


def roundtrip(kind, values):
    toks = [token(kind, v) for v in values]
    body = (str(len(toks)) + "\n" + "\n".join(toks)).encode()
    return toks, call(f"/api/roundtrip?type={kind}", body)


class EncodingsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.results = wait_results()
        cls.columns = {c["name"]: c for c in cls.results["columns"]}
        cls.values = {name: call(f"/api/column/{name}/values") for name in cls.columns}

    def enc(self, column, name):
        return next(e for e in self.columns[column]["encodings"] if e["name"] == name)

    def test_raw_bytes_match_an_independent_count(self):
        for name, c in self.columns.items():
            vals = self.values[name]
            self.assertEqual(len(vals), c["rows"])
            expected = sum(len(v.encode()) + 4 for v in vals) if c["type"] == "str" else 8 * len(vals)
            self.assertEqual(c["raw_bytes"], expected, name)

    def test_encoded_sizes_match_the_format_computed_independently_in_python(self):
        checked = 0
        for name, c in self.columns.items():
            for e in c["encodings"]:
                expected = expected_size(e["name"], self.values[name])
                if expected is not None:
                    self.assertEqual(e["bytes"], expected, f"{name}/{e['name']}")
                    checked += 1
        self.assertGreaterEqual(checked, 28)

    def test_ratio_is_raw_size_over_encoded_size(self):
        for c in self.columns.values():
            for e in c["encodings"]:
                self.assertAlmostEqual(e["ratio"], c["raw_bytes"] / e["bytes"], delta=0.001)
                self.assertGreater(e["encode_mbs"], 0)
                self.assertGreater(e["decode_mbs"], 0)

    def test_every_encoding_round_trips_real_column_slices_exactly(self):
        for name, c in self.columns.items():
            sent, got = roundtrip(c["type"], self.values[name][:SLICE])
            self.assertEqual(len(got["results"]), len(c["encodings"]))
            for r in got["results"]:
                self.assertEqual(r["values"], sent, f"{name}/{r['encoding']} changed the data")
                self.assertTrue(r["roundtrip"])
            self.assertTrue(all(e["roundtrip"] for e in c["encodings"]), name)

    def test_adversarial_values_round_trip_bit_for_bit(self):
        rng = random.Random(7)
        cases = {
            "int": [[], [0], [-(2 ** 63), 2 ** 63 - 1, -(2 ** 63), 0, -1, 2 ** 63 - 1], [rng.randrange(-(2 ** 63), 2 ** 63) for _ in range(3000)], [5] * 5000],
            "float": [[], [float("nan"), -0.0, 0.0, float("inf"), float("-inf"), 5e-324, 1e308, 0.1 + 0.2], [rng.random() for _ in range(3000)], [round(rng.uniform(-50, 50), 3) for _ in range(3000)]],
            "str": [[], [""], ["", "naive cafe ☕ 日本", "line\nbreak", "x" * 500, "ÿ\u0000"], [f"user{rng.randrange(100)}@mail.com" for _ in range(3000)]],
        }
        for kind, lists in cases.items():
            for values in lists:
                sent, got = roundtrip(kind, values)
                for r in got["results"]:
                    self.assertEqual(r["values"], sent, f"{kind}/{r['encoding']} on {values[:4]}")
                    expected = expected_size(r["encoding"], values) if values else None
                    if expected is not None:
                        self.assertEqual(r["encoded_bytes"], expected, f"{kind}/{r['encoding']}")

    def test_alp_keeps_real_doubles_exact_through_exceptions(self):
        rng = random.Random(11)
        values = [rng.random() for _ in range(2048)]
        sent, got = roundtrip("float", values)
        alp = next(r for r in got["results"] if r["encoding"] == "alp")
        self.assertEqual(alp["values"], sent)
        self.assertNotIn(" 0 exceptions", alp["detail"])

    def test_each_column_is_won_by_the_encoding_built_for_its_shape(self):
        expected = {"sorted_ints": "delta", "timestamps": "delta", "day_keys": "rle", "low_card_strings": "dict", "urls_emails": "fsst", "prices": "alp"}
        for name, best in expected.items():
            self.assertEqual(self.columns[name]["best"], best, name)
            winner = self.enc(name, best)
            self.assertTrue(winner["roundtrip"])
            self.assertEqual(winner["bytes"], min(e["bytes"] for e in self.columns[name]["encodings"]))
        self.assertGreater(self.enc("urls_emails", "fsst")["ratio"], 3)
        self.assertEqual(self.enc("urls_emails", "fsst")["bytes"], min(e["bytes"] for e in self.columns["urls_emails"]["encodings"]))
        self.assertLess(self.enc("prices", "alp")["bytes"], self.enc("prices", "dict")["bytes"])
        self.assertIn(" 0 exceptions", self.enc("prices", "alp")["detail"])

    def test_nothing_beats_the_entropy_of_random_integers(self):
        bound = 64 / math.log2(1_000_000_000)
        best = self.enc("random_ints", self.columns["random_ints"]["best"])
        self.assertIn(best["name"], ["for", "bitpack", "delta"])
        self.assertLessEqual(max(e["ratio"] for e in self.columns["random_ints"]["encodings"]), bound)
        self.assertGreater(best["ratio"], bound * 0.95)

    def test_duckdb_loaded_exactly_the_same_values(self):
        for name, c in self.columns.items():
            vals = self.values[name]
            if c["type"] == "int":
                checksum = sum(vals)
            elif c["type"] == "float":
                checksum = sum(round(v * 100) for v in vals)
            else:
                checksum = sum(len(v.encode()) for v in vals)
            self.assertEqual(c["duckdb"]["count"], len(vals), name)
            self.assertEqual(int(c["duckdb"]["checksum"]), checksum, name)

    def test_duckdb_and_parquet_choose_the_same_family_of_encoding(self):
        storage = {name: {s["compression"] for s in c["duckdb"]["storage"]} for name, c in self.columns.items()}
        self.assertIn("ALP", storage["prices"])
        self.assertIn("FSST", storage["urls_emails"])
        self.assertIn("Dictionary", storage["low_card_strings"])
        self.assertTrue(storage["day_keys"] & {"RLE", "Constant"})
        self.assertIn("DELTA_BINARY_PACKED", self.columns["sorted_ints"]["duckdb"]["parquet_v2"]["encodings"])
        self.assertIn("DICTIONARY", self.columns["low_card_strings"]["duckdb"]["parquet_v1"]["encodings"])
        for name in ["sorted_ints", "timestamps"]:
            ours = self.enc(name, "delta")["bytes"]
            parquet = self.columns[name]["duckdb"]["parquet_v2"]["bytes"]
            self.assertLess(abs(ours - parquet) / parquet, 0.1, name)

    def test_ui_page_has_every_tab(self):
        with urllib.request.urlopen(BASE + "/", timeout=30) as r:
            page = r.read().decode()
        for tab in ["sizes", "speed", "inside", "duck", "try"]:
            self.assertIn(f'data-tab="{tab}"', page)


if __name__ == "__main__":
    unittest.main()
