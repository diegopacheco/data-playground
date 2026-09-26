\set ON_ERROR_STOP on
SET client_min_messages = warning;
CREATE EXTENSION IF NOT EXISTS pg_search;

DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS products;

CREATE TABLE products (
  id int PRIMARY KEY,
  name text NOT NULL,
  category text NOT NULL,
  price numeric(10,2) NOT NULL,
  description text NOT NULL
);

CREATE TABLE orders (
  order_id int PRIMARY KEY,
  customer text NOT NULL,
  product text NOT NULL,
  category text NOT NULL,
  quantity int NOT NULL,
  price numeric(10,2) NOT NULL,
  ts timestamp NOT NULL,
  amount numeric(12,2) GENERATED ALWAYS AS (quantity * price) STORED,
  day date GENERATED ALWAYS AS (ts::date) STORED
);

COPY products FROM '/data/products.csv' WITH (FORMAT csv, HEADER true);
COPY orders (order_id, customer, product, category, quantity, price, ts) FROM '/data/orders.csv' WITH (FORMAT csv, HEADER true);

CREATE INDEX products_search ON products
USING paradedb (id, name, description, (category::pdb.literal), price)
WITH (key_field = 'id');

CREATE INDEX orders_search ON orders
USING paradedb (order_id, (customer::pdb.literal), (product::pdb.literal), (category::pdb.literal), quantity, price, amount, ts, day)
WITH (key_field = 'order_id');

ANALYZE products;
ANALYZE orders;

SELECT (SELECT count(*) FROM products) AS products, (SELECT count(*) FROM orders) AS orders;
