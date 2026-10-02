CREATE KEYSPACE IF NOT EXISTS sales WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1};
CREATE TABLE IF NOT EXISTS sales.orders (order_id int PRIMARY KEY, customer text, product text, category text, quantity int, price decimal, ts timestamp);
TRUNCATE sales.orders;
COPY sales.orders (order_id, customer, product, category, quantity, price, ts) FROM '/data/orders.csv' WITH HEADER = true;
SELECT count(*) FROM sales.orders;
