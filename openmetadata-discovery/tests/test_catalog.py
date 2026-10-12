import base64
import json
import os
import re
import unittest
import urllib.parse
import urllib.request
from pathlib import Path
import psycopg2

OM = os.environ.get("OM_URL", "http://r14-openmetadata:8585")
UI = os.environ.get("UI_URL", "http://localhost:8080")
PG = dict(host=os.environ.get("PG_HOST", "r14-postgres"), port=int(os.environ.get("PG_PORT", "5432")), dbname=os.environ.get("PG_DATABASE", "shop"),
          user=os.environ.get("PG_USER", "om_reader"), password=os.environ.get("PG_PASSWORD", "om_reader_password"))
CURATION = json.loads((Path(__file__).resolve().parent.parent / "app" / "curation.json").read_text())
SCHEMAS = CURATION["schemas"]
PREFIX = f"{CURATION['service']}.{CURATION['database']}."


def http(method, url, body=None, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    request = urllib.request.Request(url, data=None if body is None else json.dumps(body).encode(), method=method, headers=headers)
    with urllib.request.urlopen(request, timeout=300) as response:
        return json.loads(response.read().decode())


def sql(query, *params):
    with psycopg2.connect(**PG) as conn, conn.cursor() as cur:
        cur.execute(query, params)
        return cur.fetchall()


def words(*texts):
    return {w for t in texts if t for w in re.split(r"[^a-z0-9]+", t.lower()) if w}


class CatalogMatchesPostgres(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.token = http("POST", OM + "/api/v1/users/login", {"email": "admin@open-metadata.org", "password": base64.b64encode(b"admin").decode()})["accessToken"]
        cls.pg_tables = {f"{s}.{n}": (k, d) for s, n, k, d in sql(
            "SELECT n.nspname, c.relname, c.relkind, obj_description(c.oid, 'pg_class') FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = ANY(%s) AND c.relkind IN ('r', 'v')", SCHEMAS)}
        cls.pg_columns = {}
        for s, n, col, typ, d in sql(
                "SELECT n.nspname, c.relname, a.attname, format_type(a.atttypid, a.atttypmod), col_description(c.oid, a.attnum) FROM pg_attribute a "
                "JOIN pg_class c ON c.oid = a.attrelid JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = ANY(%s) AND c.relkind IN ('r', 'v') AND a.attnum > 0 AND NOT a.attisdropped ORDER BY a.attnum", SCHEMAS):
            cls.pg_columns.setdefault(f"{s}.{n}", []).append((col, typ, d))
        cls.pg_reads = {}
        for view, src, col in sql(
                "SELECT vn.nspname || '.' || v.relname, sn.nspname || '.' || s.relname, a.attname FROM pg_depend d "
                "JOIN pg_rewrite r ON r.oid = d.objid JOIN pg_class v ON v.oid = r.ev_class JOIN pg_namespace vn ON vn.oid = v.relnamespace "
                "JOIN pg_class s ON s.oid = d.refobjid JOIN pg_namespace sn ON sn.oid = s.relnamespace "
                "LEFT JOIN pg_attribute a ON a.attrelid = s.oid AND a.attnum = d.refobjsubid "
                "WHERE d.classid = 'pg_rewrite'::regclass AND d.refclassid = 'pg_class'::regclass AND v.oid <> s.oid "
                "AND vn.nspname = ANY(%s) AND sn.nspname = ANY(%s)", SCHEMAS, SCHEMAS):
            cls.pg_reads.setdefault(view, {}).setdefault(src, set()).update([col] if col else [])
        cls.om_tables = {}
        page = cls.om("/tables", database=PREFIX[:-1], fields="columns,tags,owners", limit=100)
        for t in page["data"]:
            if not t.get("deleted"):
                cls.om_tables[t["fullyQualifiedName"][len(PREFIX):]] = t
        cls.edges = {}
        for key, t in cls.om_tables.items():
            graph = cls.om("/lineage/table/name/" + urllib.parse.quote(t["fullyQualifiedName"]), upstreamDepth=1, downstreamDepth=0)
            names = {n["id"]: n["fullyQualifiedName"][len(PREFIX):] for n in graph.get("nodes", [])}
            for e in graph.get("upstreamEdges", []):
                cls.edges[(names[e["fromEntity"]], key)] = e.get("lineageDetails") or {}

    @classmethod
    def om(cls, path, **params):
        return http("GET", OM + "/api/v1" + path + "?" + urllib.parse.urlencode(params), token=cls.token)

    def search(self, q):
        hits = self.om("/search/query", q=q, index="table_search_index", size=50, **{"from": 0})["hits"]["hits"]
        return {h["_source"]["fullyQualifiedName"][len(PREFIX):] for h in hits if h["_source"]["fullyQualifiedName"].startswith(PREFIX)}

    def test_every_postgres_table_and_view_is_cataloged_with_its_kind(self):
        self.assertEqual(set(self.om_tables), set(self.pg_tables), "the catalog must list exactly the relations that exist in the source schemas")
        for key, (kind, _) in self.pg_tables.items():
            self.assertEqual(self.om_tables[key]["tableType"], "View" if kind == "v" else "Regular", key)

    def test_table_and_column_descriptions_equal_postgres_comments(self):
        for key, (_, comment) in self.pg_tables.items():
            self.assertEqual(self.om_tables[key].get("description"), comment, f"{key} description must come from COMMENT ON, not be typed by hand")
            got = [c.get("description") for c in self.om_tables[key]["columns"]]
            self.assertEqual(got, [d for _, _, d in self.pg_columns[key]], f"{key} column comments")

    def test_columns_keep_postgres_order_and_declared_types(self):
        for key, columns in self.pg_columns.items():
            got = [(c["name"], c["dataTypeDisplay"]) for c in self.om_tables[key]["columns"]]
            self.assertEqual(got, [(n, t) for n, t, _ in columns], f"{key} columns or types differ from format_type in pg_attribute")

    def test_view_lineage_is_exactly_the_postgres_dependency_graph(self):
        expected = {(src, view) for view, sources in self.pg_reads.items() for src in sources}
        derived = {edge for edge, details in self.edges.items() if details.get("source") == "ViewLineage"}
        self.assertEqual(derived, expected, "lineage parsed from view SQL must match what pg_depend says each view reads")

    def test_column_lineage_only_points_at_columns_the_view_really_reads(self):
        mapped = 0
        for (src, view), details in self.edges.items():
            if details.get("source") != "ViewLineage":
                continue
            view_columns = {n for n, _, _ in self.pg_columns[view]}
            for mapping in details.get("columnsLineage") or []:
                self.assertIn(mapping["toColumn"].split(".")[-1], view_columns)
                for column in mapping["fromColumns"]:
                    table, name = column[len(PREFIX):].rsplit(".", 1)
                    self.assertIn(name, self.pg_reads[view][table], f"{view} does not read {table}.{name} according to pg_depend")
                    mapped += 1
        self.assertGreater(mapped, 0, "view lineage should carry column level mappings")

    def test_manual_lineage_edge_carries_the_batch_job_sql(self):
        for spec in CURATION["lineage"]:
            details = self.edges.get((spec["from"], spec["to"]))
            self.assertIsNotNone(details, f"{spec['from']} -> {spec['to']} missing")
            self.assertEqual(details.get("source"), "Manual")
            self.assertEqual(details.get("sqlQuery"), spec["sql"])
        self.assertNotIn(("analytics.order_revenue", "analytics.daily_sales"), {(s, v) for v, srcs in self.pg_reads.items() for s in srcs},
                         "daily_sales is a table, postgres cannot know its lineage, only the manual edge can")

    def test_tags_and_glossary_terms_match_the_curation_file(self):
        glossary = CURATION["glossary"]["name"]
        for key, spec in CURATION["tables"].items():
            table = self.om_tables[key]
            self.assertEqual(sorted(t["tagFQN"] for t in table["tags"]), sorted(spec["tags"]), key)
            for label in table["tags"]:
                self.assertEqual(label["source"], "Glossary" if label["tagFQN"].startswith(glossary + ".") else "Classification", label["tagFQN"])
            columns = {c["name"]: sorted(t["tagFQN"] for t in c.get("tags") or []) for c in table["columns"]}
            for name in columns:
                self.assertEqual(columns[name], sorted(spec["columns"].get(name, [])), f"{key}.{name}")

    def test_owners_match_the_curation_file(self):
        for key, spec in CURATION["tables"].items():
            got = sorted((o["type"], o["name"]) for o in self.om_tables[key].get("owners") or [])
            self.assertEqual(got, sorted((o["type"], o["name"]) for o in spec["owners"]), key)

    def test_glossary_and_classification_hold_every_curated_term(self):
        glossary = self.om("/glossaries/name/" + CURATION["glossary"]["name"])
        terms = {t["name"] for t in self.om("/glossaryTerms", glossary=glossary["id"], limit=100)["data"]}
        self.assertEqual(terms, {t["name"] for t in CURATION["glossary"]["terms"]})
        tags = {t["name"] for t in self.om("/tags", parent=CURATION["classification"]["name"], limit=100)["data"]}
        self.assertEqual(tags, {t["name"] for t in CURATION["classification"]["tags"]})

    def test_keyword_search_finds_exactly_the_tables_whose_name_comment_or_columns_mention_the_word(self):
        for word in ["loyalty", "email", "checkout", "revenue", "merchandising", "signup", "lifetime"]:
            expected = {key for key, (_, comment) in self.pg_tables.items() if word in words(key, comment, *[n for n, _, _ in self.pg_columns[key]])}
            self.assertTrue(expected, word)
            self.assertEqual(self.search(word), expected, f"search for {word}")
        self.assertEqual(self.search("zeppelin"), set(), "a word that is nowhere in the source must find nothing")

    def test_tag_search_finds_exactly_the_tables_carrying_the_tag(self):
        for tag in ["PII.Sensitive", "Commerce.Revenue", "DataDomain.Customer", "DataDomain.Sales"]:
            expected = {key for key, spec in CURATION["tables"].items() if tag in spec["tags"] or any(tag in v for v in spec["columns"].values())}
            self.assertEqual(self.search(f"tags.tagFQN:{tag}"), expected, tag)
        for tier in ["Tier.Tier1", "Tier.Tier2"]:
            self.assertEqual(self.search(f"tier.tagFQN:{tier}"), {key for key, spec in CURATION["tables"].items() if tier in spec["tags"]}, tier)

    def test_app_api_serves_what_openmetadata_holds(self):
        app = {t["key"]: t for t in http("GET", UI + "/api/catalog")["tables"]}
        self.assertEqual(set(app), set(self.om_tables))
        for key, t in app.items():
            self.assertEqual(t["description"], self.om_tables[key].get("description"))
            self.assertEqual(t["tags"], sorted(x["tagFQN"] for x in self.om_tables[key]["tags"]))
        lineage = http("GET", UI + "/api/lineage")
        self.assertEqual({(e["from"], e["to"]) for e in lineage["edges"]}, set(self.edges))
        verify = http("GET", UI + "/api/verify")
        self.assertTrue(verify["ok"], [c for c in verify["checks"] if not c["ok"]])

    def test_ui_page_has_every_tab_and_links_to_openmetadata(self):
        with urllib.request.urlopen(UI + "/", timeout=30) as r:
            page = r.read().decode()
        for tab in ["Overview", "Catalog", "Lineage", "Search", "Glossary and Tags", "Verify"]:
            self.assertIn(f'"{tab}"', page)
        status = http("GET", UI + "/api/status")
        self.assertTrue(status["openmetadataUrl"].startswith("http://localhost:"))
        self.assertEqual(status["openmetadata"], "2.0.2")


class ReingestFollowsTheSource(unittest.TestCase):
    def test_running_the_pipeline_again_changes_nothing(self):
        before = http("GET", UI + "/api/catalog")["tables"]
        edges = http("GET", UI + "/api/lineage")["edges"]
        report = http("POST", UI + "/api/ingest")
        self.assertTrue(report["ok"], report)
        self.assertEqual(http("GET", UI + "/api/catalog")["tables"], before, "a second run must not duplicate tags, owners or tables")
        self.assertEqual(http("GET", UI + "/api/lineage")["edges"], edges)

    def test_a_changed_postgres_comment_reaches_the_catalog_on_the_next_run(self):
        admin = {**PG, "user": os.environ.get("PG_ADMIN_USER", "postgres"), "password": os.environ.get("PG_ADMIN_PASSWORD", "postgres")}
        original = sql("SELECT col_description('raw.products'::regclass, 3)")[0][0]

        def comment(text):
            with psycopg2.connect(**admin) as conn, conn.cursor() as cur:
                cur.execute("COMMENT ON COLUMN raw.products.category IS %s", (text,))

        def catalog_value():
            table = next(t for t in http("GET", UI + "/api/catalog")["tables"] if t["key"] == "raw.products")
            return next(c["description"] for c in table["columns"] if c["name"] == "category")

        try:
            comment("Merchandising category, renamed by the test")
            self.assertTrue(http("POST", UI + "/api/ingest")["ok"])
            self.assertEqual(catalog_value(), "Merchandising category, renamed by the test", "the catalog must follow the source, not keep a stale copy")
        finally:
            comment(original)
            self.assertTrue(http("POST", UI + "/api/ingest")["ok"])
        self.assertEqual(catalog_value(), original)


if __name__ == "__main__":
    unittest.main()
