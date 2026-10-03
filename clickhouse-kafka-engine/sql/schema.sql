CREATE DATABASE IF NOT EXISTS sales;

CREATE TABLE IF NOT EXISTS sales.orders_queue
(
    order_id UInt32,
    customer String,
    product String,
    category String,
    quantity UInt32,
    price Decimal(10, 2),
    ts String
)
ENGINE = Kafka
SETTINGS
    kafka_broker_list = 'i30-kafka:29092',
    kafka_topic_list = 'orders',
    kafka_group_name = 'i30-clickhouse',
    kafka_format = 'JSONEachRow',
    kafka_num_consumers = 1,
    kafka_flush_interval_ms = 1000;

CREATE TABLE IF NOT EXISTS sales.orders
(
    order_id UInt32,
    customer String,
    product String,
    category LowCardinality(String),
    quantity UInt32,
    price Decimal(10, 2),
    ts DateTime('UTC')
)
ENGINE = MergeTree
ORDER BY (category, order_id);

CREATE TABLE IF NOT EXISTS sales.category_totals
(
    category LowCardinality(String),
    total_orders UInt64,
    total_quantity UInt64,
    total_revenue Decimal(18, 2)
)
ENGINE = SummingMergeTree
ORDER BY category;

CREATE MATERIALIZED VIEW IF NOT EXISTS sales.orders_mv TO sales.orders AS
SELECT order_id, customer, product, category, quantity, price, parseDateTimeBestEffort(ts, 'UTC') AS ts
FROM sales.orders_queue;

CREATE MATERIALIZED VIEW IF NOT EXISTS sales.category_totals_mv TO sales.category_totals AS
SELECT
    category,
    count() AS total_orders,
    sum(quantity) AS total_quantity,
    sum(quantity * price) AS total_revenue
FROM sales.orders_queue
GROUP BY category;
