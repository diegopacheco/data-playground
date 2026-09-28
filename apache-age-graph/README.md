<p align="center"><img src="https://raw.githubusercontent.com/apache/age/master/img/AGE.png" alt="Apache AGE" width="320"></p>

# apache-age-graph

Apache AGE 1.8.0 turns PostgreSQL 18.6 into a graph database. This POC loads customers, products, follows and orders as plain SQL tables, builds a property graph from them in the same database, and runs openCypher queries over it: k-hop neighbors, shortest path, "customers who bought X also bought", and SQL statements that embed a `cypher()` call and join the graph result with the relational `orders` table. A small web UI draws the graph as plain SVG and highlights what each query found, and every answer is checked by tests that recompute it from the CSV files with a plain Python BFS and counters.

## How it Works

1. `app/gen.py` writes `data/customers.csv` (36), `products.csv` (24, 6 categories), `follows.csv` (74 directed edges) and `orders.csv` (181 lines) from `random.Random(2026)`, so every run has the same data.
2. `r15-age` runs the official `apache/age:release_PG18_1.8.0` image (PostgreSQL 18.6 with the AGE extension).
3. On boot `r15-app` runs `CREATE EXTENSION age`, loads the CSVs into schema `sales` with `COPY`, then creates graph `shop` and fills it from those SQL tables with Cypher `UNWIND [...] AS r CREATE ...` and `UNWIND ... MATCH ... CREATE` for the edges.
4. `(:Customer)-[:FOLLOWS]->(:Customer)` comes from `sales.follows`. `(:Customer)-[:BOUGHT {orders, quantity}]->(:Product)` is one edge per distinct customer and product, aggregated from `sales.orders` with SQL `GROUP BY`.
5. The REST API runs Cypher through `SELECT * FROM cypher('shop', $$ ... $$) AS (...)`. Results come back as `agtype`, which parses as JSON.
6. The mixed endpoint puts a Cypher k-hop match in the `FROM` clause of a SQL query and joins its ids with `sales.orders` and `sales.products`: graph reach plus relational aggregation in one statement.
7. `app/index.html` lays out the graph once with a small force simulation and redraws highlights per tab. It uses no chart or graph library.

## Architecture

![Architecture](printscreens/architecture.svg)

## Features

* Graph and SQL in one database: the graph is built from SQL tables and queried next to them, with no second store and no sync job.
* K-hop neighbors: `-[:FOLLOWS*1..k]->` with `min(length(p))` gives every reachable customer and its hop distance.
* Shortest path: a variable-length match ordered by `length(p)` with `LIMIT 1`, capped at 6 hops, returns `[n IN nodes(p) | n.id]`. The UI draws the path.
* Recommendations: `(x)<-[:BOUGHT]-(c)-[:BOUGHT]->(o)` with `count(DISTINCT c)` gives "customers who bought X also bought". The UI highlights the buyers and the products.
* Cypher inside SQL: network spend per category and "picks" (products your network bought and you did not, found with `NOT EXISTS` on `sales.orders`) come from one SQL statement that calls `cypher()`.
* Every response carries the exact Cypher or SQL text that ran, and the UI shows it.
* Safe inputs: ids and `k` are validated as bounded integers before they reach a query, and the API returns 400 otherwise.
* Lean: Postgres is capped at 512 MB and the app at 256 MB. Both used about 30 MB each after loading and the full test run.

## Stack

* Apache AGE 1.8.0 on PostgreSQL 18.6 (`docker.io/apache/age:release_PG18_1.8.0`): the latest AGE release, built for the latest PostgreSQL major.
* Python 3.14.7 (`docker.io/library/python:3.14.7-slim`): one image generates the data, serves the UI and API, and runs the tests.
* psycopg 3.3.6 (`psycopg[binary]`): the only third-party library, the PostgreSQL driver with `COPY` support.
* Python stdlib `http.server`, `unittest`, `urllib`: the server and the tests, no framework.
* Plain HTML, CSS, JS and SVG: the UI and the graph drawing.
* podman + podman-compose: run the two containers.

## Contracts / APIs

| Method | Path | Description |
|---|---|---|
| GET | `/` | UI |
| GET | `/api/stats` | Vertex and edge counts per label, SQL row counts, AGE and PostgreSQL versions |
| GET | `/api/graph` | Every vertex and edge, used to draw the graph |
| GET | `/api/khop?customer=1&k=2` | Customers reachable in 1..k FOLLOWS hops, with the minimum hop count (`k` 1..4) |
| GET | `/api/path?from=1&to=18` | Shortest FOLLOWS path as a list of customer ids, `null` when there is none within 6 hops |
| GET | `/api/recommend?product=5` | Buyers of the product and the top 5 products they also bought |
| GET | `/api/network?customer=1&k=2` | SQL plus `cypher()`: spend per category of the k-hop network, and top 5 picks |
| POST | `/api/reload` | Drops and reloads the SQL tables and the graph from `data/` |
| SQL | `postgresql://localhost:28000/graph` | PostgreSQL with AGE, user and password `graph` |

```json
GET /api/khop?customer=1&k=2
{"customer": 1, "k": 2,
 "cypher": "MATCH p = (c:Customer {id: 1})-[:FOLLOWS*1..2]->(n:Customer)\nWHERE n.id <> 1\nRETURN n.id, n.name, min(length(p))",
 "reached": [{"id": 7, "name": "Gabi", "hops": 1}, {"id": 29, "name": "Cris", "hops": 1},
             {"id": 30, "name": "Dora", "hops": 2}, {"id": 35, "name": "Ivo", "hops": 2}]}

GET /api/path?from=1&to=18
{"from": 1, "to": 18, "max_hops": 6, "path": [1, 29, 30, 13, 32, 18], "hops": 5, "cypher": "..."}
```

## Key data structures and design decisions

* SQL: `sales.customers(customer_id, name, city)`, `sales.products(product_id, name, category, price_cents)`, `sales.follows(follower_id, followed_id)` and `sales.orders(order_id, customer_id, product_id, quantity, price_cents, order_date)`, with foreign keys.
* Graph `shop`: `Customer {id, name, city}`, `Product {id, name, category, price_cents}`, `FOLLOWS` (directed), `BOUGHT {orders, quantity}`.
* BOUGHT collapses repeat purchases into one edge (181 order lines become 143 edges), so `count(DISTINCT c)` counts people, not orders. The per-order detail stays in SQL, where it is used for money.
* The SQL tables are the source of truth and the graph is derived from them on every boot (about 30 ms), so a restart always gives a consistent state.
* AGE 1.8.0 has no `shortestPath()` function. The shortest path is a bounded variable-length match ordered by length. That is fine at this size, but its cost grows with the number of paths, so it is capped at 6 hops.
* AGE takes the Cypher text as a dollar-quoted literal. Ids are validated as integers and then formatted in, which is simpler than prepared `agtype` parameters. Parameters do work with `PREPARE ... cypher('shop', $$ ... $cid ... $$, $1)`.
* `agtype` columns come back as text that is valid JSON for scalars and lists, so `json.loads` is the whole decoder.
* The graph needs a name of at least 3 characters (`create_graph('g')` fails with "graph name is invalid").
* Every container, the volume and the network start with `r15-` (`r15-age`, `r15-app`, `r15-age-data`, `r15-net`).

## How to run

Requirements: podman, podman-compose, curl and lsof. Python and psycopg run inside the containers.

```bash
./scripts/setup.sh
./scripts/start-all.sh
./scripts/test-all.sh
./scripts/ui.sh
./scripts/stop-all.sh
```

`test-all.sh` runs `tests/test_graph.py` inside `r15-app` against the live API. The expected values come from the CSV files, never from the database:

* The SQL tables hold every CSV row, and the graph has one vertex per customer and product, one FOLLOWS edge per follow row and one BOUGHT edge per distinct customer and product pair (fewer than the order lines).
* `/api/graph` returns exactly the follow pairs from the CSV, and each BOUGHT edge carries the order count and quantity summed from `orders.csv`.
* K-hop: for all 36 customers and k = 1, 2, 3, the reached set and hop counts equal a plain Python BFS.
* Shortest path: for 10 sources and every target (350 pairs), the hop count equals the BFS distance, the path starts and ends at the right customers, and every step is a real follow edge. Unreachable pairs return `null`, and the test requires that such pairs exist.
* Also bought: for all 24 products, the buyers and the top 5 co-purchased products with their counts (ties by id) equal a Python co-purchase count.
* Cypher + SQL: for all 36 customers, spend per category (buyers, order lines, revenue in cents) over the 2-hop network, and the top 5 picks the customer has not bought, equal a Python recompute.
* Bad input (`k=9`, a non-numeric id, an injection attempt) returns 400.
* The UI serves all five tabs.

The tests were also run against a tampered copy of the CSVs (one follow edge removed, one order quantity changed). 6 of the 9 tests failed, as they should.

```
test_customers_who_bought_x_also_bought_matches_co_purchase_counts_for_every_product ... ok
test_graph_endpoint_edges_and_properties_match_the_csv_files ... ok
test_graph_has_a_vertex_per_customer_and_product_and_one_bought_edge_per_distinct_pair ... ok
test_invalid_parameters_are_rejected_before_reaching_cypher ... ok
test_k_hop_reach_and_hop_count_match_a_breadth_first_search_for_every_customer ... ok
test_network_spend_joins_cypher_reach_with_sql_orders ... ok
test_shortest_path_is_as_short_as_bfs_and_walks_only_real_follows_edges ... ok
test_sql_tables_hold_every_csv_row ... ok
test_ui_page_has_every_tab ... ok

Ran 9 tests in 5.209s

OK
all tests passed
```

## Printscreens

Graph tab: all 60 vertices and 217 edges in a force layout. Customers are blue circles, products are squares colored by category, FOLLOWS edges are solid arrows and BOUGHT edges are dashed. The side panel shows the SQL row counts, the vertex and edge counts per label, and the graph schema.

![Graph](printscreens/graph.png)

K-hop tab: Ana's 3-hop reach. The source has a dark ring, and reached customers are colored by hop (1 red, 2 amber, 3 gray). Only the FOLLOWS edges inside the reach stay visible. The panel groups the 10 customers by hop and shows the Cypher that ran.

![K-hop](printscreens/khop.png)

Shortest path tab: Ana to Rosa in 5 hops (Ana, Cris, Dora, Maya, Fabi, Rosa). The path is drawn in orange over the dimmed graph. Clicking any customer sets the target.

![Shortest path](printscreens/path.png)

Also bought tab: the 5 customers who bought Espresso Beans, and the products they also bought, ranked by the number of those buyers (SQL Deep Dive and Microphone with 2). Only the BOUGHT edges involved are drawn.

![Also bought](printscreens/also.png)

Cypher + SQL tab: Ana's 3-hop network (light blue) and the products it bought that Ana has not (orange). The panel shows spend per category and the picks, both from SQL statements whose `FROM` clause is a `cypher()` call joined with `sales.orders` and `sales.products`. The full SQL text is shown below them.

![Cypher + SQL](printscreens/mix.png)

## Scripts

All scripts live in `scripts/` and run from any directory of the repository.

| Script | What it does |
|---|---|
| `./scripts/setup.sh` | Pulls the AGE and Python images, builds the app image, generates the CSVs when missing |
| `./scripts/start-all.sh` | Starts PostgreSQL with AGE and the app (which loads the tables and the graph), waits for each, and prints every link |
| `./scripts/status.sh` | Shows every service port as UP or DOWN with the pid |
| `./scripts/test-all.sh` | Runs the tests inside `r15-app` against the live API |
| `./scripts/ui.sh` | Opens the UI in the browser |
| `./scripts/sql-console.sh` | Opens psql with AGE preloaded and `ag_catalog` on the search path |
| `./scripts/stop-all.sh` | Stops every container and waits until the ports are free |

Ports are declared in `scripts/ports.env`: PostgreSQL 28000 (`postgresql://graph:graph@localhost:28000/graph`), UI 28001 (`http://localhost:28001`).

```bash
./scripts/setup.sh
./scripts/start-all.sh
./scripts/status.sh
./scripts/ui.sh
./scripts/stop-all.sh
```
