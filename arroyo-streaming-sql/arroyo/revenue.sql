CREATE TABLE orders (
  order_id BIGINT,
  customer TEXT,
  product TEXT,
  category TEXT,
  quantity BIGINT,
  price DOUBLE,
  ts TEXT
) WITH (
  connector = 'kafka',
  bootstrap_servers = 'q1-redpanda:9092',
  topic = 'orders',
  type = 'source',
  format = 'json',
  'source.offset' = 'earliest'
);

CREATE TABLE revenue_by_category WITH (
  connector = 'kafka',
  bootstrap_servers = 'q1-redpanda:9092',
  topic = 'revenue_by_category',
  type = 'sink',
  format = 'debezium_json'
);

INSERT INTO revenue_by_category
SELECT
  category,
  count(*) AS total_orders,
  sum(quantity) AS total_quantity,
  round(sum(quantity * price), 2) AS total_revenue
FROM orders
GROUP BY category;
