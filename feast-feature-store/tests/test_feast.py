import json
import os
import time
import unittest
import urllib.request
from datetime import datetime
import duckdb
import redis

DATA = os.environ.get("DATA_DIR", "/data")
UI = os.environ.get("UI_URL", "http://localhost:8080")
FEATURE_SERVER = os.environ.get("FEATURE_SERVER_URL", "http://r16-feature-server:6566")
HOURLY_TTL = 24 * 3600
DAILY_TTL = 7 * 24 * 3600


def call(path, body=None, base=UI):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(base + path, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())


def asof(con, table, ttl, columns):
    cols = ", ".join(f"CASE WHEN epoch(l.event_timestamp) - f.observed_at <= {ttl} THEN f.{c} END AS {c}" for c in columns)
    sql = f"SELECT l.request_id, {cols} FROM read_parquet('{DATA}/labels.parquet') l ASOF LEFT JOIN read_parquet('{DATA}/{table}.parquet') f ON l.driver_id = f.driver_id AND l.event_timestamp >= f.event_timestamp ORDER BY l.request_id"
    return {r[0]: r[1:] for r in con.execute(sql).fetchall()}


def latest(con, table, columns, since_epoch):
    sql = f"SELECT driver_id, {', '.join(columns)} FROM read_parquet('{DATA}/{table}.parquet') QUALIFY row_number() OVER (PARTITION BY driver_id ORDER BY event_timestamp DESC) = 1"
    return {r[0]: (r[1:] if r[-1] >= since_epoch else None) for r in con.execute(sql).fetchall()}


class FeastFeatureStore(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.state = call("/api/bootstrap", {})
        cls.con = duckdb.connect()
        cls.training = {r["request_id"]: r for r in call("/api/training")["rows"]}
        cls.summary = call("/api/training")["summary"]
        cls.labels = {r[0]: (r[1], r[2]) for r in cls.con.execute(f"SELECT request_id, driver_id, epoch(event_timestamp)::BIGINT FROM read_parquet('{DATA}/labels.parquet')").fetchall()}
        cls.start = datetime.fromisoformat(cls.state["windows"]["driver_hourly"]["start"]).timestamp()
        cls.daily_start = datetime.fromisoformat(cls.state["windows"]["driver_daily"]["start"]).timestamp()

    def test_historical_features_equal_an_independent_duckdb_asof_join_with_ttl(self):
        hourly = asof(self.con, "driver_hourly", HOURLY_TTL, ["conv_rate", "trips_today", "observed_at"])
        daily = asof(self.con, "driver_daily", DAILY_TTL, ["rating", "observed_at"])
        self.assertEqual(len(self.training), 300)
        for rid, row in self.training.items():
            self.assertEqual((row["conv_rate"], row["trips_today"], row["hourly_observed_at"]), hourly[rid], f"hourly features of request {rid}")
            self.assertEqual((row["rating"], row["daily_observed_at"]), daily[rid], f"daily features of request {rid}")

    def test_no_training_row_sees_a_feature_observed_after_its_label(self):
        for rid, row in self.training.items():
            label_epoch = self.labels[rid][1]
            for k in ("hourly_observed_at", "daily_observed_at"):
                if row[k] is not None:
                    self.assertLessEqual(row[k], label_epoch, f"request {rid} {k} is from the future")
        self.assertEqual(self.summary["pit_future_values"], 0)

    def test_a_naive_latest_value_join_would_leak_future_data(self):
        last = dict(self.con.execute(f"SELECT driver_id, max(observed_at) FROM read_parquet('{DATA}/driver_hourly.parquet') GROUP BY 1").fetchall())
        leaks = sum(1 for d, t in self.labels.values() if last[d] > t)
        self.assertGreater(leaks, 250)
        self.assertEqual(self.summary["naive_future_values"], leaks)

    def test_ttl_turns_stale_features_into_nulls_in_training(self):
        stale = self.con.execute(f"SELECT count(*) FROM read_parquet('{DATA}/labels.parquet') l WHERE NOT EXISTS (SELECT 1 FROM read_parquet('{DATA}/driver_hourly.parquet') h WHERE h.driver_id = l.driver_id AND h.event_timestamp <= l.event_timestamp AND epoch(l.event_timestamp) - h.observed_at <= {HOURLY_TTL})").fetchone()[0]
        self.assertGreater(stale, 0)
        self.assertEqual(self.summary["hourly_null_by_ttl"], stale)
        self.assertEqual(sum(1 for r in self.training.values() if r["conv_rate"] is None), stale)

    def test_online_store_holds_the_latest_row_inside_the_ttl_window(self):
        online = {r["driver_id"]: r["features"] for r in call("/api/online")["rows"]}
        hourly = latest(self.con, "driver_hourly", ["conv_rate", "acc_rate", "trips_today", "observed_at"], self.start)
        daily = latest(self.con, "driver_daily", ["rating", "lifetime_trips", "observed_at"], self.daily_start)
        self.assertEqual(sorted(online), sorted(hourly))
        for d, f in online.items():
            got = (f["driver_hourly__conv_rate"]["value"], f["driver_hourly__acc_rate"]["value"], f["driver_hourly__trips_today"]["value"], f["driver_hourly__observed_at"]["value"])
            self.assertEqual(got if f["driver_hourly__conv_rate"]["found"] else None, hourly[d], f"driver {d} hourly")
            got = (f["driver_daily__rating"]["value"], f["driver_daily__lifetime_trips"]["value"], f["driver_daily__observed_at"]["value"])
            self.assertEqual(got if f["driver_daily__rating"]["found"] else None, daily[d], f"driver {d} daily")
        self.assertEqual([d for d in sorted(hourly) if hourly[d] is None], [1017, 1018, 1019, 1020])
        self.assertEqual([d for d in sorted(daily) if daily[d] is None], [1020])

    def test_online_freshness_age_matches_the_event_timestamp_and_ttl(self):
        now = time.time()
        for row in call("/api/online")["rows"]:
            for name, f in row["features"].items():
                if f["found"]:
                    self.assertTrue(f["fresh"])
                    self.assertAlmostEqual(f["age_seconds"], now - f["event_epoch"], delta=30)
                    self.assertLessEqual(f["age_seconds"], f["ttl_seconds"])
                else:
                    self.assertIsNone(f["event_epoch"])
                    self.assertFalse(f["fresh"])

    def test_redis_has_one_key_per_driver_with_any_fresh_feature(self):
        hourly = latest(self.con, "driver_hourly", ["observed_at"], self.start)
        daily = latest(self.con, "driver_daily", ["observed_at"], self.daily_start)
        expected = sum(1 for d in hourly if hourly[d] is not None or daily[d] is not None)
        self.assertEqual(redis.Redis(host=os.environ.get("REDIS_HOST", "r16-redis")).dbsize(), expected)

    def test_feast_feature_server_returns_what_the_sdk_returns(self):
        ids = [1001, 1007, 1017, 1020]
        sdk = {r["driver_id"]: r["features"] for r in call("/api/online?driver_ids=" + ",".join(map(str, ids)))["rows"]}
        http = call("/get-online-features", {"feature_service": "driver_model_v1", "entities": {"driver_id": ids}, "full_feature_names": True}, FEATURE_SERVER)
        names = http["metadata"]["feature_names"]
        for col, name in enumerate(names):
            if name == "driver_id":
                continue
            for i, d in enumerate(ids):
                self.assertEqual(http["results"][col]["statuses"][i], sdk[d][name]["status"], f"{name} {d}")
                if sdk[d][name]["found"]:
                    self.assertEqual(http["results"][col]["values"][i], sdk[d][name]["value"], f"{name} {d}")

    def test_online_lookup_latency_is_low(self):
        lat = call("/api/latency?n=100")
        self.assertEqual(lat["sdk_ms"]["n"], 100)
        self.assertLess(lat["sdk_ms"]["p50"], 25)
        self.assertLess(lat["feature_server_ms"]["p50"], 50)

    def test_registry_holds_the_declared_ttls_and_feature_service(self):
        d = call("/api/definitions")
        ttls = {v["name"]: v["ttl_seconds"] for v in d["feature_views"]}
        self.assertEqual(ttls, {"driver_hourly": HOURLY_TTL, "driver_daily": DAILY_TTL})
        self.assertEqual(d["entities"][0]["join_key"], "driver_id")
        self.assertEqual(sorted(d["feature_services"][0]["views"]), ["driver_daily", "driver_hourly"])

    def test_ui_page_has_every_tab(self):
        with urllib.request.urlopen(UI + "/", timeout=10) as r:
            html = r.read().decode()
        for tab in ("Point-in-time", "Online serving", "Definitions"):
            self.assertIn(tab, html)

    def test_zz_push_makes_a_stale_driver_fresh_online_but_not_in_offline_data(self):
        try:
            before = call("/api/online?driver_ids=1017")["rows"][0]["features"]["driver_hourly__conv_rate"]
            self.assertFalse(before["found"])
            call("/api/push", {"driver_id": 1017, "conv_rate": 0.4242, "acc_rate": 0.9, "trips_today": 7})
            after = call("/api/online?driver_ids=1017")["rows"][0]["features"]
            self.assertEqual(after["driver_hourly__conv_rate"]["value"], 0.4242)
            self.assertEqual(after["driver_hourly__trips_today"]["value"], 7)
            self.assertTrue(after["driver_hourly__conv_rate"]["fresh"])
            self.assertLess(after["driver_hourly__conv_rate"]["age_seconds"], 30)
            offline = self.con.execute(f"SELECT count(*) FROM read_parquet('{DATA}/driver_hourly.parquet') WHERE driver_id = 1017 AND conv_rate = 0.4242").fetchone()[0]
            self.assertEqual(offline, 0)
        finally:
            call("/api/bootstrap", {})


if __name__ == "__main__":
    unittest.main()
