SELECT setseed(0.43);
SET synchronous_commit = off;
INSERT INTO shop.order_items (id, order_id, product_id, quantity, unit_price)
SELECT x.g, x.order_id, x.product_id, x.quantity, p.price
FROM (
  SELECT g,
         CASE WHEN g <= 1500000 THEN g ELSE 1 + floor(random() * 1500000)::bigint END AS order_id,
         1 + floor(power(random(), 2.2) * 25000)::int AS product_id,
         CASE WHEN random() < 0.8 THEN 1 ELSE 2 + floor(random() * 4)::int END AS quantity
  FROM generate_series(1, 5000000) g
) x
JOIN shop.products p ON p.id = x.product_id;
