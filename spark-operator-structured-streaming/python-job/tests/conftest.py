from collections.abc import Iterator
from pathlib import Path

import pytest
from pyspark.sql import SparkSession

ICEBERG = "org.apache.iceberg:iceberg-spark-runtime-4.1_2.13:1.12.0"


@pytest.fixture(scope="session")
def root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("lake")


@pytest.fixture(scope="session")
def spark(root: Path) -> Iterator[SparkSession]:
    session = (
        SparkSession.builder.master("local[2]")
        .appName("streamjob-tests")
        .config("spark.ui.enabled", "false")
        .config("spark.sql.shuffle.partitions", "2")
        .config("spark.sql.session.timeZone", "UTC")
        .config("spark.jars.packages", ICEBERG)
        .config("spark.sql.extensions", "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions")
        .config("spark.sql.catalog.lake", "org.apache.iceberg.spark.SparkCatalog")
        .config("spark.sql.catalog.lake.type", "hadoop")
        .config("spark.sql.catalog.lake.warehouse", (root / "warehouse").as_uri())
        .config("spark.sql.catalog.lake.cache-enabled", "false")
        .getOrCreate()
    )
    yield session
    session.stop()
