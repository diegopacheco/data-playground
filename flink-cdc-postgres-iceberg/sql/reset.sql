BEGIN;

CREATE TEMP TABLE staging (LIKE orders) ON COMMIT DROP;
COPY staging FROM '/data/orders.csv' WITH (FORMAT csv, HEADER true);

DELETE FROM orders WHERE order_id NOT IN (SELECT order_id FROM staging);

INSERT INTO orders SELECT * FROM staging
ON CONFLICT (order_id) DO UPDATE SET
  customer = EXCLUDED.customer,
  product = EXCLUDED.product,
  category = EXCLUDED.category,
  quantity = EXCLUDED.quantity,
  price = EXCLUDED.price,
  ts = EXCLUDED.ts
WHERE (orders.customer, orders.product, orders.category, orders.quantity, orders.price, orders.ts)
  IS DISTINCT FROM (EXCLUDED.customer, EXCLUDED.product, EXCLUDED.category, EXCLUDED.quantity, EXCLUDED.price, EXCLUDED.ts);

COMMIT;
