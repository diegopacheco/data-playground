import json
from functools import cache
from typing import Any

from lake_e2e import config
from lake_e2e.kube import kubectl

QUERY = "/opt/jobs/python/streamjob/query.py"


@cache
def spark_submit() -> list[str]:
    manifest = json.loads(kubectl("create", "--dry-run=client", "-o", "json", "-f", str(config.MANIFESTS["java"])))
    confs = [arg for key, value in manifest["spec"]["sparkConf"].items() for arg in ("--conf", f"{key}={value}")]
    return ["/opt/spark/bin/spark-submit", "--master", "local[2]", "--driver-memory", "1g", "--conf", "spark.ui.enabled=false", *confs]


def parse_rows(output: str, statements: int) -> list[list[dict[str, Any]]]:
    results: list[list[dict[str, Any]]] = [[] for _ in range(statements)]
    for line in output.splitlines():
        if line.startswith("ROW "):
            _, index, payload = line.split(" ", 2)
            results[int(index)].append(json.loads(payload))
    return results


def query(*statements: str) -> list[list[dict[str, Any]]]:
    return parse_rows(kubectl("exec", "deploy/lake-query", "--", *spark_submit(), QUERY, *statements, timeout=600), len(statements))


def table_exists(table: str) -> bool:
    namespace, name = table.rsplit(".", 1)
    rows = query(f"SHOW TABLES IN {namespace}")[0]
    return any(r.get("tableName") == name for r in rows)


def snapshots_sql(table: str) -> str:
    return (
        "SELECT unix_millis(committed_at) AS commit_ms,"
        " CAST(summary['added-data-files'] AS BIGINT) AS files,"
        " CAST(summary['added-files-size'] AS BIGINT) AS bytes,"
        " CAST(summary['added-records'] AS BIGINT) AS records,"
        " summary['spark.sql.streaming.queryId'] AS query_id,"
        " CAST(summary['spark.sql.streaming.epochId'] AS BIGINT) AS epoch"
        f" FROM {table}.snapshots ORDER BY committed_at"
    )


def latency_sql(table: str) -> str:
    return (
        "SELECT unix_millis(t.event_time) AS event_ms, unix_millis(s.committed_at) AS commit_ms"
        f" FROM {table} t"
        f" JOIN {table}.entries e ON t._file = e.data_file.file_path AND e.status < 2"
        f" JOIN {table}.snapshots s ON e.snapshot_id = s.snapshot_id"
    )


def counts_sql(table: str) -> str:
    return (
        "SELECT count(*) AS total, count(DISTINCT id) AS ids,"
        " count(DISTINCT kafka_partition, kafka_offset) AS offsets"
        f" FROM {table}"
    )


def partitions_sql(table: str) -> str:
    return (
        "SELECT kafka_partition AS p, min(kafka_offset) AS lo, max(kafka_offset) AS hi, count(*) AS n"
        f" FROM {table} GROUP BY kafka_partition ORDER BY kafka_partition"
    )
