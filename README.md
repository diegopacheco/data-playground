# data-playground

Hands-on POCs of the modern data stack. Every project runs locally in podman, has its own README and ships with a small UI.

## 🧊 Lakehouse & Table Formats

Table formats turn plain Parquet files on S3 into real tables.
They add ACID, schema evolution and time travel.

* [iceberg-spark-minio](iceberg-spark-minio/) - Spark 4.1 + Scala 3 writing an Iceberg table on MinIO
* [iceberg-pyiceberg-duckdb](iceberg-pyiceberg-duckdb/) - PyIceberg writes, DuckDB reads, snapshots and time travel
* [delta-spark-minio](delta-spark-minio/) - Delta Lake on Spark: MERGE, Change Data Feed, history, time travel
* [delta-rs-python](delta-rs-python/) - Delta Lake from pure Python with delta-rs, no Spark, no JVM
* [hudi-spark-cow-mor](hudi-spark-cow-mor/) - Hudi Copy-On-Write vs Merge-On-Read benchmark
* [paimon-flink-lakehouse](paimon-flink-lakehouse/) - Streaming lakehouse with Paimon 2.0 + Flink 2.2 from Kafka
* [ducklake-duckdb](ducklake-duckdb/) - DuckLake: a table format with a SQL database as catalog
* [xtable-iceberg-delta-hudi](xtable-iceberg-delta-hudi/) - Write once as Hudi, read as Delta and Iceberg with XTable
* [medallion-bronze-silver-gold](medallion-bronze-silver-gold/) - Bronze, silver and gold layers on Iceberg with Spark

## 📚 Catalogs

A catalog keeps track of where every table lives and what version is current.
It lets many engines share the same tables safely.

* [iceberg-rest-catalog-polaris](iceberg-rest-catalog-polaris/) - Apache Polaris: Spark writes, Trino reads the same table
* [iceberg-trino-nessie](iceberg-trino-nessie/) - Project Nessie: git-like branches and merges for data
* [lakekeeper-iceberg-catalog](lakekeeper-iceberg-catalog/) - Lakekeeper: Rust Iceberg REST catalog with MinIO STS

## 🕸️ Governance & Lineage

Governance tools record who owns each dataset and which ones hold personal data.
Lineage shows which job built each table and where its data came from.

* [gravitino-openlineage-marquez](gravitino-openlineage-marquez/) - Gravitino owners and tags, OpenLineage events, lineage graph in Marquez

## ⚙️ Batch Engines

Engines read data, run the heavy computation and write the results.
They range from one laptop process to a whole cluster.

* [spark-scala-cassandra](spark-scala-cassandra/) - Spark + Scala 3 batch job into Cassandra
* [beam-java-pipeline](beam-java-pipeline/) - Apache Beam + Java 25 batch job into Postgres
* [trino-federated-join](trino-federated-join/) - One Trino query joining Postgres, Cassandra and Iceberg
* [duckdb-vs-polars-vs-datafusion](duckdb-vs-polars-vs-datafusion/) - Same queries on 10M rows, three engines benchmarked
* [daft-multimodal-dataframe](daft-multimodal-dataframe/) - Daft dataframe mixing tables, images and embeddings

## 🌊 Stream Processing

Stream processors handle events one by one, as they arrive.
They keep running totals instead of waiting for a nightly batch.

* [flink-java-cassandra](flink-java-cassandra/) - Flink 2.3 + Java 25 into Cassandra
* [kafka-streams-java-cassandra](kafka-streams-java-cassandra/) - Kafka Streams + Java 25 into Cassandra
* [spark-redpanda-cassandra](spark-redpanda-cassandra/) - Spark reads a Redpanda topic into Cassandra
* [arroyo-streaming-sql](arroyo-streaming-sql/) - Arroyo streaming SQL over Redpanda
* [bytewax-python-streaming](bytewax-python-streaming/) - Bytewax dataflows in Python over Redpanda

## 🔁 Change Data Capture

CDC reads the database log and turns every insert, update and delete into an event.
Other systems stay in sync without polling the source.

* [debezium-kafka-cassandra](debezium-kafka-cassandra/) - Debezium: MySQL binlog to Kafka to Cassandra
* [flink-cdc-postgres-iceberg](flink-cdc-postgres-iceberg/) - Flink CDC: Postgres 18 to Iceberg in upsert mode

## ⚡ Real-Time OLAP

OLAP databases answer aggregate queries over lots of rows in milliseconds.
They power dashboards and user-facing analytics.

* [clickhouse-kafka-engine](clickhouse-kafka-engine/) - ClickHouse Kafka engine with materialized views
* [druid-rollup-ingestion](druid-rollup-ingestion/) - Apache Druid rollup vs raw ingestion
* [pinot-realtime-olap](pinot-realtime-olap/) - Apache Pinot REALTIME table consuming Kafka
* [doris-olap-stream-load](doris-olap-stream-load/) - Apache Doris Stream Load with a materialized view

## 📥 Ingestion

Ingestion tools copy data from databases and APIs into your warehouse or lake.
They load only what changed and follow the source schema as it grows.

* [dlt-python-ingest](dlt-python-ingest/) - dlt loads Postgres and a REST API into DuckDB with merge and schema evolution

## 🎼 Orchestration

Orchestrators decide what runs, when, and in which order.
They retry failures and show the state of every pipeline run.

* [airflow-python-cassandra](airflow-python-cassandra/) - Apache Airflow DAG into Cassandra
* [dagster-assets-iceberg](dagster-assets-iceberg/) - Dagster assets building Iceberg tables with checks
* [prefect-python-314-etl](prefect-python-314-etl/) - Prefect 3 ETL flow on Python 3.14
* [kestra-yaml-pipelines](kestra-yaml-pipelines/) - Kestra pipelines written only in YAML
* [temporal-java-25-etl](temporal-java-25-etl/) - Temporal durable workflow ETL in Java 25

## 🛠️ Transformation

Transformation tools turn raw tables into clean models using SQL.
They add tests, dependencies and versioning on top of plain queries.

* [dbt-python-cassandra](dbt-python-cassandra/) - dbt models with results stored in Cassandra
* [dbt-spark-iceberg](dbt-spark-iceberg/) - dbt on Spark writing incremental Iceberg tables
* [sqlmesh-vs-dbt](sqlmesh-vs-dbt/) - Same models in SQLMesh and dbt, compared

## 🧭 Vector & Search

Vector databases find things by meaning, not by exact words.
Search engines rank text matches with scores like BM25.

* [pgvector-embeddings-pipeline](pgvector-embeddings-pipeline/) - Local embeddings into Postgres 18 with pgvector
* [qdrant-vector-search](qdrant-vector-search/) - Qdrant semantic, hybrid and recommend search
* [paradedb-search-analytics](paradedb-search-analytics/) - ParadeDB BM25 search and analytics inside Postgres

## 📦 File Formats & Data Transport

File formats decide how data is laid out on disk and how well it compresses.
Arrow moves columnar data between systems without converting it.

* [parquet-rust-arrow](parquet-rust-arrow/) - Parquet and Arrow from Rust with arrow-rs
* [parquet-vs-orc-vs-avro](parquet-vs-orc-vs-avro/) - Parquet vs ORC vs Avro on 1M rows
* [lance-vs-vortex-vs-parquet](lance-vs-vortex-vs-parquet/) - Lance vs Vortex vs Parquet: size, scans, random access, vector search
* [arrow-flight-java-python](arrow-flight-java-python/) - Arrow Flight server in Java, client in Python

## 🗄️ Databases

Specialized databases built for one job and built to do it very fast.
Here: wide-column storage and a financial ledger.

* [scylladb-vs-cassandra-bench](scylladb-vs-cassandra-bench/) - ScyllaDB vs Cassandra on the same workload
* [tigerbeetle-ledger-ingest](tigerbeetle-ledger-ingest/) - TigerBeetle double-entry ledger for orders
