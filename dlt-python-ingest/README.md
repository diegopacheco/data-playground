<p align="center"><img src="https://raw.githubusercontent.com/dlt-hub/dlt/devel/docs/website/static/img/dlthub-logo.png" alt="dlt" height="80"></p>

# dlt-python-ingest

Code first EL with [dlt](https://dlthub.com) (data load tool) 1.30 on Python 3.14. One dlt pipeline loads two real sources into a DuckDB file: the `orders` table of a Postgres 18 database (seeded from `data/orders.csv`) through dlt's `sql_database` source, and a small paginated REST API with nested JSON customers (served by this POC) through dlt's `rest_api` source. It shows incremental loading with an `updated_at` cursor, the `merge` write disposition with primary keys (updates and deletes never duplicate), automatic schema inference and evolution, nested JSON normalized into child tables, and load packages tracked in `_dlt_loads`. A single page UI runs the pipeline, changes the sources, and shows runs, loads, tables, row counts and the schema versions.

## How it Works

1. On start `app/server.py` seeds Postgres from `data/orders.csv` into `orders` (with `updated_at = ts` and a `deleted` flag) and derives 20 `customers` rows with `addresses` and `tags` as jsonb.
2. The same server exposes `GET /source/customers?updated_since=&page=&page_size=`, a paginated JSON API over `customers` (5 per page, with `pages` in the body).
3. `app/pipeline.py` declares one dlt source `shop` with two resources: `sql_table("orders")` with `dlt.sources.incremental("updated_at")`, `write_disposition="merge"`, `primary_key="order_id"` and the `hard_delete` hint on `deleted`, and a `rest_api` resource `customers` with a `page_number` paginator, an incremental `updated_since` query param bound to `updated_at` and merge on `id`.
4. `POST /api/run` calls `pipeline.run(shop())`: dlt extracts only rows newer than the stored cursor, normalizes them (infers types, flattens `loyalty` into `loyalty__points`, moves the `addresses` and `tags` lists into child tables), writes a load package and merges it into DuckDB (`shop.duckdb`, dataset `ingest`).
5. `POST /api/changes` changes the sources: 3 orders are updated, 2 are soft deleted, 2 are inserted, a new `coupon` column is added to `orders`, and 2 customers get a new tier, a new `loyalty` object and one more address.
6. The next run loads only those rows, merges them in place, removes the deleted orders, and dlt adds the new columns and stores a new schema version in `_dlt_version`.
7. The UI reads `_dlt_loads`, `_dlt_version`, the pipeline schema and the tables straight from DuckDB.

## Architecture

![Architecture](printscreens/architecture.svg)

## Features

* Incremental loading: the `updated_at` cursor is kept in the pipeline state (also stored in `_dlt_pipeline_state` in DuckDB), so a rerun with no source changes loads 0 rows.
* Merge with primary key: `orders` merges on `order_id`, `customers` on `id`, so an updated source row replaces its destination row instead of appending a copy.
* Deletes: the source soft deletes with `deleted = true`, and the `hard_delete` column hint makes the merge delete that row downstream.
* Schema inference: dlt infers every column type (from SQLAlchemy reflection for Postgres, from the JSON values for the API, `updated_at` strings become `timestamp`), no DDL is written by hand.
* Schema evolution: a column added in Postgres (`coupon`) and a new nested object in the API (`loyalty`) become new destination columns on the next run, recorded as a new version in `_dlt_version`.
* Nested JSON: the `addresses` and `tags` lists become `customers__addresses` and `customers__tags`, linked by `_dlt_parent_id`, and a merge replaces the child rows of an updated parent.
* Load packages: every run commits one load package, each row carries its `_dlt_load_id`, and `_dlt_loads` holds one completed row per load.
* One source, two resources: both sources share one schema (`shop`) and one load package per run.

## Stack

* dlt 1.30.0 (`dlt[duckdb,sql-database]`): latest release on PyPI, supports Python 3.10 to 3.14, EL as plain Python with incremental, merge and schema evolution built in.
* Python 3.14.7 (`python:3.14.7-slim`): pipeline, REST source and UI server in one image.
* DuckDB 1.5.5: destination, a single file (`shop.duckdb`) in the `r4-dlt-state` volume, nothing else to run.
* Postgres 18.6 (`postgres:18.6-alpine`): the source database, capped at 256 MB.
* SQLAlchemy 2.1.1 + psycopg2-binary 2.9.13: used by the `sql_database` source to reflect and read `orders`. SQLAlchemy 2.1 defaults `postgresql://` to psycopg 3, so the pipeline passes `postgresql+psycopg2://`.
* Python stdlib `http.server`: serves the UI, the JSON API and the REST source.
* Plain HTML, CSS and JS for the UI, no framework.
* podman + podman-compose: runs Postgres and the app.

## Contracts / APIs

| Method | Path | Description |
|---|---|---|
| GET | `/` | UI |
| GET | `/source/customers?updated_since=&page=1&page_size=5` | REST source read by dlt: `{"data": [...], "page", "page_size", "total", "pages"}`, customers with `updated_at >= updated_since` ordered by id |
| POST | `/api/run` | Runs the dlt pipeline and returns the load info of that run |
| POST | `/api/changes` | Updates 3, soft deletes 2 and inserts 2 orders, adds `orders.coupon`, updates 2 customers, returns what changed |
| POST | `/api/reset` | Reseeds Postgres from the CSV and removes the DuckDB file and the pipeline state |
| GET | `/api/overview` | Versions, source counts, every run, `_dlt_loads` and every destination table with its row count |
| GET | `/api/schema` | Current dlt schema (tables, columns, types, hints) and every version in `_dlt_version` with the columns it added |
| GET | `/api/sql?q=` | Read only SQL (`SELECT`, `WITH`, `DESCRIBE`, `SHOW`) on the DuckDB destination |

Load info returned by `POST /api/run` after `POST /api/changes`:

```json
{"run": 3, "finished_at": "2026-09-26T05:11:00+00:00", "duration_ms": 638.1, "load_ids": ["1790399460.2595184"],
 "row_counts": {"orders": 7, "customers": 2, "customers__addresses": 5, "customers__tags": 2},
 "schema_version": 4, "schema_hash": "K84AqvFNvLwAILL+rdnxoZC6MKaIz8sSZwsjYRA+YnM=",
 "new_columns": ["orders.coupon", "customers.loyalty__level", "customers.loyalty__points"], "failed_jobs": false}
```

One customer from the REST source after a change:

```json
{"id": 2, "name": "Bruno Silva", "email": "bruno.silva@mail.test", "tier": "platinum",
 "addresses": [{"zip": "1014", "city": "Madrid", "kind": "home"}, {"zip": "2022", "city": "Rome", "kind": "work"},
               {"zip": "D02", "city": "Dublin", "kind": "shipping"}],
 "tags": ["sports"], "updated_at": "2026-09-26T05:11:20.606635+00:00", "loyalty": {"level": "platinum", "points": 120}}
```

## Key data structures and design decisions

* Destination tables (dataset `ingest`): `orders`, `customers`, `customers__addresses`, `customers__tags`, plus dlt's `_dlt_loads`, `_dlt_version` and `_dlt_pipeline_state`. Every row has `_dlt_id` and `_dlt_load_id`, child rows have `_dlt_parent_id`, `_dlt_root_id` and `_dlt_list_idx`.
* DuckDB over a Postgres destination: one file, no extra container, and dlt's merge on DuckDB supports `hard_delete` and child tables the same way.
* The pipeline runs inside the UI process behind one lock, so the single DuckDB writer never races with the UI reads. The REST source path does not take that lock, because the pipeline calls it while holding it.
* The cursor boundary: both sources return `updated_at >= cursor`, and dlt drops the rows it already loaded at that exact timestamp with the `unique_hashes` kept in the state, so nothing is lost when several rows share a timestamp and nothing is loaded twice.
* The API omits `loyalty` until a customer has one, so the new columns appear only when the data does, which is how schema evolution looks with a real API.
* One source `shop` with both resources gives one schema and one load package per run, instead of one schema per source.
* The pipeline working dir, the DuckDB file and `runs.json` live in the `r4-dlt-state` volume, so a restart keeps the pipeline state and the history.
* Containers `r4-postgres` (256 MB) and `r4-app` (768 MB, about 125 MB used), volumes `r4-pgdata` and `r4-dlt-state`, network `r4-net`. Ports: Postgres 26900, UI 26901.

## How to run

Requirements: podman, podman-compose, curl, lsof and python3 (the tests use only the standard library).

```bash
./scripts/setup.sh
./scripts/start-all.sh
./scripts/test-all.sh
./scripts/ui.sh
./scripts/stop-all.sh
```

`test-all.sh` resets everything and plays one scenario: run, rerun with no changes, change the sources, run, run again. The tests use the CSV and the REST source as the independent truth and query DuckDB with their own SQL:

* The first run loads every CSV order exactly once with the CSV values, and every page of the REST source.
* A rerun without changes loads 0 rows and keeps the counts, the run after the changes loads only the 7 changed orders and the 2 changed customers.
* Updated orders have the new quantity and coupon in a single row, soft deleted orders are gone, inserted orders are there, and `count(DISTINCT order_id) = count(*) = live source rows`.
* `coupon` is missing after the first run and present after the change (null only for the untouched rows), `loyalty__points` and `loyalty__level` hold the new values, and the change is a new version in `_dlt_version` with a new hash.
* Child tables hold exactly the number of list items the API returns, with no orphans, and an updated customer has its new address list, not the old one plus the new one.
* Every load id returned by a run is a completed row in `_dlt_loads`, the rows of the change run carry that run's `_dlt_load_id`, and the cursor stored in `_dlt_pipeline_state` equals the max `updated_at` loaded.
* After the Python tests, the script compares the source counts from `psql` with the DuckDB counts.

When `write_disposition` is switched to `append` and the incremental cursor is removed, 9 of these tests fail.

```
test_first_run_loads_every_csv_order_exactly_once ... ok
test_loaded_values_match_the_csv ... ok
test_rest_source_is_paginated_and_every_page_is_loaded ... ok
test_rerun_without_source_changes_loads_nothing_and_duplicates_nothing ... ok
test_run_after_changes_only_loads_the_changed_rows ... ok
test_every_loaded_row_points_to_a_committed_load ... ok
test_every_run_commits_one_completed_load_package ... ok
test_incremental_cursor_is_stored_in_the_destination_state ... ok
test_destination_mirrors_live_source_rows_without_duplicates ... ok
test_soft_deleted_source_rows_are_removed_from_the_destination ... ok
test_updated_source_rows_replace_the_destination_row ... ok
test_merge_replaces_the_child_rows_of_an_updated_parent ... ok
test_nested_lists_become_child_tables_linked_to_their_parent ... ok
test_evolution_is_recorded_as_a_new_schema_version ... ok
test_new_nested_json_object_is_flattened_into_new_columns ... ok
test_new_source_column_is_added_to_the_destination_table ... ok
Ran 16 tests in 3.016s
OK
csv rows (awk): 200, source live orders (psql): 200, soft deleted: 2, destination orders (duckdb): 200
source customers (psql): 20, destination customers (duckdb): 20
all tests passed
```

## Printscreens

Runs and loads. Run 1 loads 200 orders, 20 customers, 30 addresses and 26 tags. Run 2 has no source changes and loads nothing. Run 3 comes after Apply source changes: 7 orders (3 updated, 2 deleted, 2 inserted), 2 customers with their 5 addresses and 2 tags, and three new columns, with the schema going from v2 to v4. Each run is one completed row in `_dlt_loads`, with the schema hash it was loaded with.

![Runs and loads](printscreens/runs-and-loads.png)

Destination tables with row counts. Clicking a table previews it, here `customers__addresses`, the child table dlt made from the `addresses` list, with `_dlt_parent_id` pointing to the customer row and `_dlt_list_idx` keeping the list order.

![Destination tables](printscreens/destination-tables.png)

A SQL query on the destination: the 3 updated orders (quantity + 1, coupon SAVE10) and the 2 inserted orders (WELCOME) carry the load id of the change run, all the other orders keep the first load id and a null coupon.

![Destination SQL](printscreens/destination-sql.png)

Schema and evolution. `_dlt_version` holds the initial schema (30 inferred columns) and the version that added `orders.coupon`, `customers.loyalty__level` and `customers.loyalty__points`. Below it, every table of the current schema with its write disposition, the inferred types and the hints dlt uses: `primary_key`, `incremental`, `hard_delete`, `row_key`, `parent_key`, and the new columns highlighted.

![Schema evolution](printscreens/schema-evolution.png)

Sources, right after Apply source changes: live and soft deleted orders in Postgres, the ids that were updated, deleted and inserted, the customers that got a loyalty object, and the first page of the REST source as dlt reads it.

![Sources](printscreens/sources.png)

Run pipeline after that second change: run 5 loads again only the 7 changed orders and the 2 changed customers, no new columns this time since the schema already has them, and the destination still holds exactly 200 orders.

![Run after changes](printscreens/run-after-changes.png)

## Scripts

All scripts live in `scripts/` and run from any directory of the repository.

| Script | What it does |
|---|---|
| `./scripts/setup.sh` | Pulls the Postgres and Python images and builds the app image |
| `./scripts/start-all.sh` | Starts Postgres and the app, runs the pipeline when it never ran, and prints the full link of each service |
| `./scripts/pipeline.sh` | Runs the dlt pipeline once and prints its load info |
| `./scripts/status.sh` | Shows every service port as UP or DOWN |
| `./scripts/test-all.sh` | Runs the ingest scenario tests and compares the Postgres counts with DuckDB |
| `./scripts/ui.sh` | Opens the UI in the browser |
| `./scripts/sql-console.sh` | Opens psql in the Postgres source container |
| `./scripts/stop-all.sh` | Stops every service |

Ports are declared in `scripts/ports.env` (postgres 26900, ui 26901). Postgres is at `postgresql://shop:shop@localhost:26900/shop`, the UI at `http://localhost:26901`.

```bash
./scripts/setup.sh
./scripts/start-all.sh
./scripts/status.sh
./scripts/ui.sh
./scripts/sql-console.sh
./scripts/stop-all.sh
```
