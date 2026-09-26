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
* [fluss-flink-paimon](fluss-flink-paimon/) - Apache Fluss 1.0 streaming storage tiered into Paimon, with union read
* [ducklake-duckdb](ducklake-duckdb/) - DuckLake: a table format with a SQL database as catalog
* [pg-lake-postgres-iceberg](pg-lake-postgres-iceberg/) - pg_lake: Postgres 18 writes Iceberg and Parquet on MinIO, joins them with heap tables
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
* [openmetadata-discovery](openmetadata-discovery/) - OpenMetadata catalog of Postgres with tags, glossary, owners, search and view lineage

## ⚙️ Batch Engines

Engines read data, run the heavy computation and write the results.
They range from one laptop process to a whole cluster.

* [spark-scala-cassandra](spark-scala-cassandra/) - Spark + Scala 3 batch job into Cassandra
* [beam-java-pipeline](beam-java-pipeline/) - Apache Beam + Java 25 batch job into Postgres
* [trino-federated-join](trino-federated-join/) - One Trino query joining Postgres, Cassandra and Iceberg
* [duckdb-vs-polars-vs-datafusion](duckdb-vs-polars-vs-datafusion/) - Same queries on 10M rows, three engines benchmarked
* [sail-vs-spark-connect](sail-vs-spark-connect/) - Same PySpark job on Spark 4.2 and on Sail (Rust), benchmarked
* [daft-multimodal-dataframe](daft-multimodal-dataframe/) - Daft dataframe mixing tables, images and embeddings

## 🌊 Stream Processing

Stream processors handle events one by one, as they arrive.
They keep running totals instead of waiting for a nightly batch.

* [flink-java-cassandra](flink-java-cassandra/) - Flink 2.3 + Java 25 into Cassandra
* [kafka-streams-java-cassandra](kafka-streams-java-cassandra/) - Kafka Streams + Java 25 into Cassandra
* [spark-redpanda-cassandra](spark-redpanda-cassandra/) - Spark reads a Redpanda topic into Cassandra
* [arroyo-streaming-sql](arroyo-streaming-sql/) - Arroyo streaming SQL over Redpanda
* [bytewax-python-streaming](bytewax-python-streaming/) - Bytewax dataflows in Python over Redpanda

## 📨 Messaging & Streaming Storage

Brokers keep an ordered log of events that many readers can replay.
Schema registries make sure producers and consumers keep agreeing on the data shape.

* [pulsar-tiered-storage](pulsar-tiered-storage/) - Apache Pulsar: brokers apart from BookKeeper, old ledgers offloaded to MinIO and read back
* [nats-jetstream-streams](nats-jetstream-streams/) - NATS JetStream cluster: retention modes, acks and redelivery, replay, KV and failover
* [automq-diskless-kafka](automq-diskless-kafka/) - AutoMQ: Kafka with no data on broker disks, all of it on S3, survives broker replacement
* [schema-registry-avro-protobuf](schema-registry-avro-protobuf/) - Apicurio Registry: Avro and Protobuf evolution under BACKWARD, FORWARD, FULL and NONE

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

## ✅ Data Quality

Data contracts say what a good batch looks like before anyone uses it.
Bad batches get blocked and quarantined instead of reaching the dashboards.

* [pandera-quality-gates-medallion](pandera-quality-gates-medallion/) - Pandera contracts as bronze, silver and gold gates on DuckDB, with row-level failure reports

## 🧭 Vector & Search

Vector databases find things by meaning, not by exact words.
Search engines rank text matches with scores like BM25.

* [pgvector-embeddings-pipeline](pgvector-embeddings-pipeline/) - Local embeddings into Postgres 18 with pgvector
* [qdrant-vector-search](qdrant-vector-search/) - Qdrant semantic, hybrid and recommend search
* [paradedb-search-analytics](paradedb-search-analytics/) - ParadeDB BM25 search and analytics inside Postgres

## 🤖 Feature Stores

Feature stores serve the same ML features for training and for live predictions.
Training data is joined point-in-time so no value comes from the future.

* [feast-feature-store](feast-feature-store/) - Feast with DuckDB offline and Redis online stores, point-in-time joins and TTLs

## 📦 File Formats & Data Transport

File formats decide how data is laid out on disk and how well it compresses.
Arrow moves columnar data between systems without converting it.

* [parquet-rust-arrow](parquet-rust-arrow/) - Parquet and Arrow from Rust with arrow-rs
* [parquet-vs-orc-vs-avro](parquet-vs-orc-vs-avro/) - Parquet vs ORC vs Avro on 1M rows
* [lance-vs-vortex-vs-parquet](lance-vs-vortex-vs-parquet/) - Lance vs Vortex vs Parquet: size, scans, random access, vector search
* [arrow-flight-java-python](arrow-flight-java-python/) - Arrow Flight server in Java, client in Python

## 🗄️ Databases

Specialized databases built for one job and built to do it very fast.
Here: wide-column storage, a financial ledger and a graph.

* [scylladb-vs-cassandra-bench](scylladb-vs-cassandra-bench/) - ScyllaDB vs Cassandra on the same workload
* [tigerbeetle-ledger-ingest](tigerbeetle-ledger-ingest/) - TigerBeetle double-entry ledger for orders
* [sql-playground](sql-playground/) - PostgreSQL 18 workbench with plans, timing, hints, 8 contention races and every join type
* [apache-age-graph](apache-age-graph/) - Apache AGE: openCypher graph and SQL tables in one Postgres 18

## 🧮 Fundamentals

How data systems work on the inside, built from scratch or measured against the exact answer.
Encodings, sketches and reprocessing patterns show up under every tool above.

* [columnar-encodings-from-scratch](columnar-encodings-from-scratch/) - RLE, dictionary, delta, bit-packing, FSST and ALP in Rust, compared with DuckDB and Parquet
* [datasketches-hll-kll-theta](datasketches-hll-kll-theta/) - Apache DataSketches HLL, KLL, Theta and Count-Min vs exact answers on 10M events
* [kappa-vs-lambda-backfill](kappa-vs-lambda-backfill/) - Kappa vs Lambda: idempotent backfills, late data and a bug fix by log replay
