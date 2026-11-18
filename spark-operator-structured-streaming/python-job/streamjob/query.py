import json
import sys
from datetime import datetime
from typing import Any

from pyspark.sql import Row, SparkSession


def plain(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Row):
        return {k: plain(v) for k, v in value.asDict().items()}
    if isinstance(value, dict):
        return {str(k): plain(v) for k, v in value.items()}
    if isinstance(value, list):
        return [plain(v) for v in value]
    return value


def main(statements: list[str]) -> None:
    spark = SparkSession.builder.appName("lake-query").getOrCreate()
    spark.sparkContext.setLogLevel("ERROR")
    for index, statement in enumerate(statements):
        for row in spark.sql(statement).collect():
            print(f"ROW {index} {json.dumps(plain(row))}", flush=True)
    spark.stop()


if __name__ == "__main__":
    main(sys.argv[1:])
