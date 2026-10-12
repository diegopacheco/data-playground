\connect shop

CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
CREATE SCHEMA raw;
CREATE SCHEMA analytics;
COMMENT ON SCHEMA raw IS 'Tables loaded as-is from the web shop OLTP system';
COMMENT ON SCHEMA analytics IS 'Views and tables derived from raw for reporting';

CREATE TABLE raw.customers (
  customer_id integer PRIMARY KEY,
  full_name varchar(120) NOT NULL,
  email varchar(200) NOT NULL,
  country varchar(2) NOT NULL,
  signup_date date NOT NULL
);
COMMENT ON TABLE raw.customers IS 'People who registered an account in the web shop';
COMMENT ON COLUMN raw.customers.customer_id IS 'Surrogate key of the customer';
COMMENT ON COLUMN raw.customers.full_name IS 'First and last name as typed at signup';
COMMENT ON COLUMN raw.customers.email IS 'Login email, unique per customer';
COMMENT ON COLUMN raw.customers.country IS 'ISO 3166 two letter country code of the shipping address';
COMMENT ON COLUMN raw.customers.signup_date IS 'Day the account was created';

CREATE TABLE raw.products (
  product_id integer PRIMARY KEY,
  name varchar(120) NOT NULL,
  category varchar(40) NOT NULL,
  unit_price numeric(10,2) NOT NULL
);
COMMENT ON TABLE raw.products IS 'Catalog of sellable items with their current list price';
COMMENT ON COLUMN raw.products.product_id IS 'Surrogate key of the product';
COMMENT ON COLUMN raw.products.name IS 'Display name shown on the storefront';
COMMENT ON COLUMN raw.products.category IS 'Merchandising category such as books or games';
COMMENT ON COLUMN raw.products.unit_price IS 'Current list price in USD';

CREATE TABLE raw.orders (
  order_id integer PRIMARY KEY,
  customer_id integer NOT NULL REFERENCES raw.customers(customer_id),
  order_date date NOT NULL,
  status varchar(20) NOT NULL
);
COMMENT ON TABLE raw.orders IS 'Checkout events, one row per basket submitted';
COMMENT ON COLUMN raw.orders.order_id IS 'Surrogate key of the order';
COMMENT ON COLUMN raw.orders.customer_id IS 'Customer who placed the order';
COMMENT ON COLUMN raw.orders.order_date IS 'Day the order was placed';
COMMENT ON COLUMN raw.orders.status IS 'completed, cancelled or returned';

CREATE TABLE raw.order_items (
  order_id integer NOT NULL REFERENCES raw.orders(order_id),
  product_id integer NOT NULL REFERENCES raw.products(product_id),
  quantity integer NOT NULL,
  unit_price numeric(10,2) NOT NULL,
  PRIMARY KEY (order_id, product_id)
);
COMMENT ON TABLE raw.order_items IS 'Line items of each order with the price paid at checkout';
COMMENT ON COLUMN raw.order_items.order_id IS 'Order the line belongs to';
COMMENT ON COLUMN raw.order_items.product_id IS 'Product that was bought';
COMMENT ON COLUMN raw.order_items.quantity IS 'Units bought';
COMMENT ON COLUMN raw.order_items.unit_price IS 'Price paid per unit in USD';

CREATE VIEW analytics.order_revenue AS
SELECT o.order_id, o.customer_id, o.order_date, SUM(i.quantity * i.unit_price) AS revenue
FROM raw.orders o JOIN raw.order_items i ON i.order_id = o.order_id
WHERE o.status = 'completed'
GROUP BY o.order_id, o.customer_id, o.order_date;
COMMENT ON VIEW analytics.order_revenue IS 'Revenue of every completed order';
COMMENT ON COLUMN analytics.order_revenue.order_id IS 'Completed order';
COMMENT ON COLUMN analytics.order_revenue.customer_id IS 'Customer who placed the order';
COMMENT ON COLUMN analytics.order_revenue.order_date IS 'Day the order was placed';
COMMENT ON COLUMN analytics.order_revenue.revenue IS 'Sum of quantity times price paid';

CREATE VIEW analytics.customer_lifetime_value AS
SELECT c.customer_id, c.full_name, c.country, COUNT(r.order_id) AS orders, COALESCE(SUM(r.revenue), 0) AS lifetime_revenue
FROM raw.customers c LEFT JOIN analytics.order_revenue r ON r.customer_id = c.customer_id
GROUP BY c.customer_id, c.full_name, c.country;
COMMENT ON VIEW analytics.customer_lifetime_value IS 'Loyalty scoring input: completed orders and revenue per customer';
COMMENT ON COLUMN analytics.customer_lifetime_value.customer_id IS 'Customer key';
COMMENT ON COLUMN analytics.customer_lifetime_value.full_name IS 'Customer name';
COMMENT ON COLUMN analytics.customer_lifetime_value.country IS 'Shipping country';
COMMENT ON COLUMN analytics.customer_lifetime_value.orders IS 'Number of completed orders';
COMMENT ON COLUMN analytics.customer_lifetime_value.lifetime_revenue IS 'Revenue of all completed orders';

CREATE VIEW analytics.product_sales AS
SELECT p.category, p.name, SUM(i.quantity) AS units, SUM(i.quantity * i.unit_price) AS revenue
FROM raw.order_items i JOIN raw.products p ON p.product_id = i.product_id
GROUP BY p.category, p.name;
COMMENT ON VIEW analytics.product_sales IS 'Units and revenue per product for merchandising';
COMMENT ON COLUMN analytics.product_sales.category IS 'Merchandising category';
COMMENT ON COLUMN analytics.product_sales.name IS 'Product name';
COMMENT ON COLUMN analytics.product_sales.units IS 'Units sold across all orders';
COMMENT ON COLUMN analytics.product_sales.revenue IS 'Revenue across all orders';

CREATE TABLE analytics.daily_sales (
  sales_date date PRIMARY KEY,
  orders integer NOT NULL,
  revenue numeric(12,2) NOT NULL
);
COMMENT ON TABLE analytics.daily_sales IS 'Nightly snapshot of completed revenue per day, loaded by the finance batch job';
COMMENT ON COLUMN analytics.daily_sales.sales_date IS 'Calendar day';
COMMENT ON COLUMN analytics.daily_sales.orders IS 'Completed orders that day';
COMMENT ON COLUMN analytics.daily_sales.revenue IS 'Completed revenue that day in USD';

INSERT INTO raw.customers VALUES
  (1, 'Ana Souza', 'ana@shop.test', 'BR', '2026-01-04'),
  (2, 'Ben Carter', 'ben@shop.test', 'US', '2026-01-19'),
  (3, 'Chloe Martin', 'chloe@shop.test', 'FR', '2026-02-02'),
  (4, 'Diego Lima', 'diego@shop.test', 'BR', '2026-03-11');
INSERT INTO raw.products VALUES
  (10, 'Data Engineering Book', 'books', 45.00),
  (11, 'Mechanical Keyboard', 'hardware', 120.00),
  (12, 'Strategy Board Game', 'games', 60.00);
INSERT INTO raw.orders VALUES
  (100, 1, '2026-04-01', 'completed'),
  (101, 2, '2026-04-01', 'completed'),
  (102, 1, '2026-04-02', 'cancelled'),
  (103, 3, '2026-04-02', 'completed'),
  (104, 4, '2026-04-03', 'returned');
INSERT INTO raw.order_items VALUES
  (100, 10, 2, 45.00), (100, 12, 1, 55.00), (101, 11, 1, 120.00),
  (102, 10, 1, 45.00), (103, 12, 2, 60.00), (104, 11, 1, 110.00);
INSERT INTO analytics.daily_sales
SELECT order_date, COUNT(*), SUM(revenue) FROM analytics.order_revenue GROUP BY order_date;

GRANT USAGE ON SCHEMA raw, analytics TO om_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA raw, analytics TO om_reader;
GRANT pg_read_all_stats TO om_reader;
