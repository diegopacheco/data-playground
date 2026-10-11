import io
import json
import math
import threading
from datetime import datetime, timezone
from pathlib import Path
import duckdb
import pandas as pd
import pandera.pandas as pa
from contracts import bronze_contract, catalog, gold_contract, silver_contract

TABLES = """
CREATE TABLE bronze (batch_id VARCHAR, row_num INTEGER, record JSON, landed_at TIMESTAMP);
CREATE TABLE silver (batch_id VARCHAR, order_id VARCHAR, customer_id VARCHAR, order_ts TIMESTAMP, region VARCHAR, product VARCHAR, quantity BIGINT, unit_price DOUBLE, currency VARCHAR);
CREATE TABLE quarantine (batch_id VARCHAR, row_num INTEGER, blocked_at VARCHAR, failed_checks JSON, record JSON);
CREATE TABLE gold (day VARCHAR, region VARCHAR, orders BIGINT, units BIGINT, revenue DOUBLE);
CREATE TABLE batches (batch_id VARCHAR PRIMARY KEY, file VARCHAR, extracted_at TIMESTAMP, rows INTEGER, status VARCHAR, blocked_at VARCHAR, report JSON, processed_at TIMESTAMP);
"""

GOLD_SQL = """
SELECT strftime(order_ts, '%Y-%m-%d') AS day, region, count(*) AS orders, sum(quantity) AS units, round(sum(quantity * unit_price), 2) AS revenue
FROM silver GROUP BY 1, 2 ORDER BY 1, 2
"""

LAYERS = {
    "bronze": "SELECT batch_id, row_num, record, landed_at FROM bronze ORDER BY batch_id, row_num",
    "silver": "SELECT * FROM silver ORDER BY batch_id, order_id",
    "quarantine": "SELECT batch_id, row_num, blocked_at, failed_checks, record FROM quarantine ORDER BY json_array_length(failed_checks) DESC, batch_id, row_num",
    "gold": "SELECT * FROM gold ORDER BY day, region",
}


class Rejected(Exception):
    pass


def clean(value):
    if value is None or (isinstance(value, float) and math.isnan(value)) or value is pd.NaT:
        return None
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    if hasattr(value, "item"):
        return value.item()
    return value


def check_key(row):
    column = row["column"] if isinstance(row["column"], str) and row.get("schema_context") != "DataFrameSchema" else "*"
    check = str(row["check"])
    if check.startswith(("dtype(", "coerce_dtype(")):
        check = "dtype"
    if check in ("column_in_schema", "column_in_dataframe"):
        column = "*"
    if check == "multiple_fields_uniqueness":
        column, check = "*", "duplicates"
    return column, check


def gate(name, schema, df):
    report = {"gate": name, "contract": schema.name, "passed": True, "skipped": False, "checks": []}
    failures = pd.DataFrame(columns=["column", "check", "failure_case", "index"])
    validated = None
    try:
        validated = schema.validate(df, lazy=True)
    except pa.errors.SchemaErrors as e:
        failures = e.failure_cases
        report["passed"] = False
    grouped = {}
    for row in failures.to_dict(orient="records"):
        grouped.setdefault(check_key(row), []).append(row)
    entries = catalog(schema)
    known = {(e["column"], e["check"]) for e in entries}
    entries += [{"column": c, "check": k, "label": k} for c, k in grouped if (c, k) not in known]
    for entry in entries:
        rows = grouped.get((entry["column"], entry["check"]), [])
        row_nums = sorted({int(r["index"]) for r in rows if clean(r["index"]) is not None})
        samples = []
        for r in rows:
            value = clean(r["failure_case"])
            if value not in samples:
                samples.append(value)
        report["checks"].append({**entry, "passed": not rows, "failures": len(rows), "rows": row_nums, "samples": samples[:6]})
    return report, validated


def skipped(name, schema):
    return {"gate": name, "contract": schema.name, "passed": None, "skipped": True, "checks": [{**e, "passed": None, "failures": 0, "rows": [], "samples": []} for e in catalog(schema)]}


class Pipeline:
    def __init__(self, path, incoming):
        self.lock = threading.Lock()
        self.incoming = Path(incoming)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.con = duckdb.connect(path)

    def reset(self):
        with self.lock:
            for table in ["bronze", "silver", "quarantine", "gold", "batches"]:
                self.con.execute(f"DROP TABLE IF EXISTS {table}")
            self.con.execute(TABLES)

    def run_all(self):
        self.reset()
        manifest = json.loads((self.incoming / "manifest.json").read_text())
        for entry in manifest:
            text = (self.incoming / entry["file"]).read_text()
            self.ingest(entry["batch_id"], entry["extracted_at"], text, entry["file"])
        return self.summary()

    def incoming_files(self):
        return json.loads((self.incoming / "manifest.json").read_text())

    def incoming_csv(self, batch_id):
        for entry in self.incoming_files():
            if entry["batch_id"] == batch_id:
                return (self.incoming / entry["file"]).read_text()
        return None

    def ingest(self, batch_id, extracted_at, text, file="api"):
        with self.lock:
            return self._ingest(batch_id, extracted_at, text, file)

    def _ingest(self, batch_id, extracted_at, text, file):
        if not batch_id or self.con.execute("SELECT 1 FROM batches WHERE batch_id = ?", [batch_id]).fetchone():
            raise Rejected(f"batch_id '{batch_id}' is empty or already processed")
        try:
            extracted = pd.Timestamp(extracted_at).tz_localize(None) if pd.Timestamp(extracted_at).tzinfo else pd.Timestamp(extracted_at)
            raw = pd.read_csv(io.StringIO(text), dtype=str)
        except Exception as e:
            raise Rejected(f"unreadable batch: {e}")
        raw.index = range(1, len(raw) + 1)
        records = {i: {k: clean(v) for k, v in row.items()} for i, row in zip(raw.index, raw.to_dict(orient="records"))}
        landed = datetime.now(timezone.utc).replace(tzinfo=None)
        self.con.executemany("INSERT INTO bronze VALUES (?, ?, ?, ?)", [[batch_id, i, json.dumps(r), landed] for i, r in records.items()])
        promoted = [r[0] for r in self.con.execute("SELECT order_id FROM silver").fetchall()]
        bronze_report, _ = gate("bronze", bronze_contract(), raw)
        silver_schema = silver_contract(extracted, promoted)
        gates = [bronze_report]
        blocked = None
        if not bronze_report["passed"]:
            blocked = "bronze"
            gates += [skipped("silver", silver_schema), skipped("gold", gold_contract(0, 0.0))]
        else:
            silver_report, typed = gate("silver", silver_schema, raw.copy())
            gates.append(silver_report)
            if not silver_report["passed"]:
                blocked = "silver"
                gates.append(skipped("gold", gold_contract(0, 0.0)))
            else:
                gold_report = self._promote(batch_id, typed)
                gates.append(gold_report)
                if not gold_report["passed"]:
                    blocked = "gold"
        if blocked:
            self._quarantine(batch_id, blocked, records, gates)
        failed = [f"{c['column']}: {c['label']}" for g in gates for c in g["checks"] if c["passed"] is False]
        report = {"batch_id": batch_id, "file": file, "extracted_at": extracted.isoformat(), "rows": len(raw),
                  "status": "quarantined" if blocked else "promoted", "blocked_at": blocked, "failed_checks": failed, "gates": gates}
        self.con.execute("INSERT INTO batches VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                         [batch_id, file, extracted.to_pydatetime(), len(raw), report["status"], blocked, json.dumps(report), landed])
        return report

    def _promote(self, batch_id, typed):
        frame = typed.assign(batch_id=batch_id)[["batch_id", "order_id", "customer_id", "order_ts", "region", "product", "quantity", "unit_price", "currency"]]
        frame = frame.astype({c: object for c in ["batch_id", "order_id", "customer_id", "region", "product", "currency"]})
        self.con.execute("BEGIN TRANSACTION")
        self.con.register("incoming_batch", frame)
        self.con.execute("INSERT INTO silver SELECT * FROM incoming_batch")
        self.con.unregister("incoming_batch")
        candidate = self.con.execute(GOLD_SQL).df()
        orders, revenue = self.con.execute("SELECT count(*), coalesce(sum(quantity * unit_price), 0) FROM silver").fetchone()
        report, _ = gate("gold", gold_contract(int(orders), float(revenue)), candidate)
        if report["passed"]:
            self.con.execute("DELETE FROM gold")
            self.con.execute(f"INSERT INTO gold {GOLD_SQL}")
            self.con.execute("COMMIT")
        else:
            self.con.execute("ROLLBACK")
        return report

    def _quarantine(self, batch_id, blocked, records, gates):
        per_row = {i: [] for i in records}
        batch_level = []
        for g in gates:
            for c in g["checks"]:
                if c["passed"] is False:
                    name = f"{g['gate']} | {c['column']}: {c['label']}"
                    if c["rows"]:
                        for i in c["rows"]:
                            per_row.setdefault(i, []).append(name)
                    else:
                        batch_level.append(name)
        self.con.executemany("INSERT INTO quarantine VALUES (?, ?, ?, ?, ?)",
                             [[batch_id, i, blocked, json.dumps(per_row[i] + batch_level), json.dumps(r)] for i, r in records.items()])

    def summary(self):
        with self.lock:
            counts = {t: self.con.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in ["bronze", "silver", "quarantine", "gold"]}
            revenue = self.con.execute("SELECT coalesce(round(sum(revenue), 2), 0) FROM gold").fetchone()[0]
            batches = [json.loads(r[0]) for r in self.con.execute("SELECT report FROM batches ORDER BY processed_at, batch_id").fetchall()]
        return {
            "layers": counts,
            "gold_revenue": float(revenue),
            "batches": [{k: b[k] for k in ["batch_id", "file", "extracted_at", "rows", "status", "blocked_at", "failed_checks"]} for b in batches],
        }

    def batch(self, batch_id):
        with self.lock:
            row = self.con.execute("SELECT report FROM batches WHERE batch_id = ?", [batch_id]).fetchone()
        return json.loads(row[0]) if row else None

    def batches(self):
        with self.lock:
            return [json.loads(r[0]) for r in self.con.execute("SELECT report FROM batches ORDER BY processed_at, batch_id").fetchall()]

    def layer(self, name, limit):
        with self.lock:
            cur = self.con.execute(f"SELECT * FROM ({LAYERS[name]}) LIMIT ?", [limit])
            columns = [d[0] for d in cur.description]
            rows = [[clean(v) for v in r] for r in cur.fetchall()]
            total = self.con.execute(f"SELECT count(*) FROM {name}").fetchone()[0]
        return {"layer": name, "columns": columns, "rows": rows, "total": total}
