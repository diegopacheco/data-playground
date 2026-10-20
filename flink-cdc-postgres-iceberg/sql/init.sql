CREATE TABLE orders (
  order_id INT PRIMARY KEY,
  customer TEXT NOT NULL,
  product TEXT NOT NULL,
  category TEXT NOT NULL,
  quantity INT NOT NULL,
  price NUMERIC(10,2) NOT NULL,
  ts TIMESTAMP NOT NULL
);

ALTER TABLE orders REPLICA IDENTITY FULL;

COPY orders FROM '/data/orders.csv' WITH (FORMAT csv, HEADER true);
