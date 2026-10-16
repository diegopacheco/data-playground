DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS customers;

CREATE TABLE customers (
  customer_id INT PRIMARY KEY,
  name VARCHAR NOT NULL,
  email VARCHAR NOT NULL,
  national_id VARCHAR NOT NULL,
  phone VARCHAR NOT NULL,
  country VARCHAR NOT NULL,
  credit_card VARCHAR NOT NULL,
  balance NUMERIC(10,2) NOT NULL
);

CREATE TABLE orders (
  order_id INT PRIMARY KEY,
  customer_id INT NOT NULL REFERENCES customers(customer_id),
  country VARCHAR NOT NULL,
  product VARCHAR NOT NULL,
  amount NUMERIC(10,2) NOT NULL,
  order_date DATE NOT NULL
);

COPY customers FROM '/data/customers.csv' WITH (FORMAT csv, HEADER true);
COPY orders FROM '/data/orders.csv' WITH (FORMAT csv, HEADER true);
