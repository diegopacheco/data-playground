import json
import os
import subprocess
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

import psycopg
from psycopg import Connection, sql

CONTEXT = os.environ.get("KUBE_CONTEXT", "kind-cronjob-watermark-microbatch")
LOADER_APPS = "app in (java-loader,python-loader)"


@dataclass(frozen=True)
class Consistency:
    missing: int
    orphan: int
    ahead: int
    expected: int
    loaded: int


@dataclass(frozen=True)
class Fingerprint:
    rows: int
    digest: str


@dataclass(frozen=True)
class Run:
    rows_loaded: int
    pages: int
    duration_ms: int


def kubectl(*args: str, stdin: str | None = None) -> str:
    result = subprocess.run(
        ["kubectl", "--context", CONTEXT, *args], input=stdin, capture_output=True, text=True
    )
    if result.returncode != 0:
        raise RuntimeError(f"kubectl {' '.join(args)} failed: {result.stderr}")
    return result.stdout


def connect() -> Connection:
    return psycopg.connect(
        host="localhost",
        port=os.environ.get("DB_PORT", "27590"),
        dbname="microbatch",
        user="microbatch",
        password="microbatch",
        application_name="e2e",
        autocommit=True,
    )


def wait_for(what: str, check: Callable[[], bool], timeout_s: int) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if check():
            return
        time.sleep(1)
    raise TimeoutError(f"timed out after {timeout_s}s waiting for {what}")


def table(job: str) -> sql.Identifier:
    return sql.Identifier(f"target_{job}")


def watermark(conn: Connection, job: str) -> tuple[datetime, int]:
    row = conn.execute("SELECT last_updated_at, last_id FROM watermarks WHERE job = %s", (job,)).fetchone()
    if row is None:
        raise RuntimeError(f"no watermark for {job}")
    return row[0], row[1]


def consistency(conn: Connection, job: str) -> Consistency:
    query = sql.SQL(
        """
        WITH wm AS (SELECT last_updated_at AS ts, last_id AS id FROM watermarks WHERE job = %s),
        expected AS (SELECT s.* FROM source_events s, wm WHERE (s.updated_at, s.id) <= (wm.ts, wm.id))
        SELECT
          (SELECT count(*) FROM expected e WHERE NOT EXISTS (
             SELECT 1 FROM {t} t WHERE t.id = e.id AND t.account = e.account
               AND t.amount_cents = e.amount_cents AND t.updated_at = e.updated_at)),
          (SELECT count(*) FROM {t} t WHERE NOT EXISTS (SELECT 1 FROM source_events s WHERE s.id = t.id)),
          (SELECT count(*) FROM {t} t, wm WHERE (t.updated_at, t.id) > (wm.ts, wm.id)),
          (SELECT count(*) FROM expected),
          (SELECT count(*) FROM {t})
        """
    ).format(t=table(job))
    row = conn.execute(query, (job,)).fetchone()
    if row is None:
        raise RuntimeError("consistency query returned no row")
    return Consistency(*row)


def fingerprint(conn: Connection, job: str) -> Fingerprint:
    query = sql.SQL(
        "SELECT count(*), coalesce(md5(string_agg(id || ':' || account || ':' || amount_cents || ':' || updated_at, ',' "
        "ORDER BY id)), '') FROM {}"
    ).format(table(job))
    row = conn.execute(query).fetchone()
    if row is None:
        raise RuntimeError("fingerprint query returned no row")
    return Fingerprint(row[0], row[1])


def last_run(conn: Connection, job_name: str) -> Run:
    row = conn.execute(
        "SELECT rows_loaded, pages, duration_ms FROM batch_runs WHERE runner LIKE %s ORDER BY id DESC LIMIT 1",
        (f"{job_name}-%",),
    ).fetchone()
    if row is None:
        raise RuntimeError(f"no batch_runs row for {job_name}")
    return Run(*row)


def cron_runs_with_rows(conn: Connection, job: str) -> int:
    row = conn.execute(
        "SELECT count(*) FROM batch_runs WHERE job = %s AND runner LIKE %s AND rows_loaded > 0",
        (job, f"{job}-loader-%"),
    ).fetchone()
    return 0 if row is None else row[0]


def job_finished(name: str) -> bool:
    status = json.loads(kubectl("get", "job", name, "-o", "json"))["status"]
    if status.get("failed"):
        logs = kubectl("logs", f"job/{name}", "--tail=40")
        raise RuntimeError(f"job {name} failed: {logs}")
    return bool(status.get("succeeded"))


def start_job(job: str, env: dict[str, str] | None = None) -> str:
    name = f"manual-{job}-{uuid.uuid4().hex[:8]}"
    spec = json.loads(kubectl("create", "job", name, f"--from=cronjob/{job}-loader", "--dry-run=client", "-o", "json"))
    container = spec["spec"]["template"]["spec"]["containers"][0]
    overrides = env or {}
    container["env"] = [e for e in container["env"] if e["name"] not in overrides] + [
        {"name": k, "value": v} for k, v in overrides.items()
    ]
    kubectl("create", "-f", "-", stdin=json.dumps(spec))
    return name


def run_job(job: str, env: dict[str, str] | None = None) -> str:
    name = start_job(job, env)
    wait_for(f"job {name} to succeed", lambda: job_finished(name), 180)
    return name


def kill_job(name: str) -> None:
    kubectl("delete", "pod", "-l", f"job-name={name}", "--grace-period=0", "--force")
    kubectl("delete", "job", name, "--wait=false")


def backend_state(conn: Connection, job: str) -> list[str]:
    rows = conn.execute(
        "SELECT state FROM pg_stat_activity WHERE application_name = %s", (f"loader-{job}",)
    ).fetchall()
    return [r[0] for r in rows]


def loader_pods_running() -> bool:
    phases = kubectl("get", "pods", "-l", LOADER_APPS, "-o", "jsonpath={.items[*].status.phase}").split()
    return any(p in ("Pending", "Running") for p in phases)


def suspend_cronjobs(suspend: bool) -> None:
    for job in ("java", "python"):
        kubectl("patch", "cronjob", f"{job}-loader", "-p", json.dumps({"spec": {"suspend": suspend}}))


def scale_generator(replicas: int) -> None:
    kubectl("scale", "deployment/generator", f"--replicas={replicas}")


def generator_gone() -> bool:
    return kubectl("get", "pods", "-l", "app=generator", "-o", "name").strip() == ""
