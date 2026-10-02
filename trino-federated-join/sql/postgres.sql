CREATE TABLE IF NOT EXISTS customers (
  customer_id INTEGER PRIMARY KEY,
  customer_name TEXT NOT NULL UNIQUE,
  region TEXT NOT NULL,
  tier TEXT NOT NULL
);
TRUNCATE customers;
COPY customers FROM '/data/customers.csv' WITH (FORMAT csv, HEADER true);
SELECT count(*) AS customers FROM customers;
