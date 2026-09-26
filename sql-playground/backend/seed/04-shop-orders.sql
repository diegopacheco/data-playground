SELECT setseed(0.44);
SET synchronous_commit = off;
INSERT INTO shop.orders (id, customer_id, status, total, item_count, created_at, shipped_at)
SELECT o.order_id,
       1 + floor(power(random(), 1.3) * 250000)::bigint,
       s.status,
       o.total,
       o.item_count,
       o.created_at,
       CASE WHEN s.status IN ('shipped', 'delivered') THEN o.created_at + (1 + random() * 96) * interval '1 hour' END
FROM (
  SELECT order_id,
         sum(quantity * unit_price) AS total,
         count(*)::int AS item_count,
         timestamptz '2021-01-01' + (order_id / 1500000.0) * interval '1800 days' + random() * interval '90 minutes' AS created_at,
         random() AS r
  FROM shop.order_items
  GROUP BY order_id
) o
CROSS JOIN LATERAL (
  SELECT CASE WHEN o.r < 0.70 THEN 'delivered' WHEN o.r < 0.82 THEN 'shipped' WHEN o.r < 0.90 THEN 'paid' WHEN o.r < 0.96 THEN 'pending' ELSE 'cancelled' END AS status
) s;
