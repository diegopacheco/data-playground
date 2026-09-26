SELECT setseed(0.45);
SET synchronous_commit = off;
INSERT INTO shop.payments (id, order_id, method, status, amount, paid_at)
SELECT row_number() OVER (ORDER BY o.id), o.id,
       CASE WHEN r < 0.55 THEN 'card' WHEN r < 0.75 THEN 'pix' WHEN r < 0.88 THEN 'paypal' WHEN r < 0.96 THEN 'bank_transfer' ELSE 'gift_card' END,
       CASE WHEN r2 < 0.965 THEN 'approved' WHEN r2 < 0.995 THEN 'refunded' ELSE 'chargeback' END,
       o.total,
       o.created_at + (1 + random() * 30) * interval '1 minute'
FROM (SELECT id, total, created_at, random() AS r, random() AS r2 FROM shop.orders WHERE status IN ('paid', 'shipped', 'delivered')) o;

INSERT INTO shop.reviews (id, product_id, customer_id, rating, title, created_at)
SELECT row_number() OVER (ORDER BY oi.id), oi.product_id, o.customer_id,
       CASE WHEN r < 0.05 THEN 1 WHEN r < 0.12 THEN 2 WHEN r < 0.27 THEN 3 WHEN r < 0.60 THEN 4 ELSE 5 END,
       (ARRAY['Terrible','Not great','It is fine','Really good','Love it'])[CASE WHEN r < 0.05 THEN 1 WHEN r < 0.12 THEN 2 WHEN r < 0.27 THEN 3 WHEN r < 0.60 THEN 4 ELSE 5 END],
       o.shipped_at + (2 + random() * 20) * interval '1 day'
FROM (SELECT id, order_id, product_id, random() AS r FROM shop.order_items WHERE id % 7 = 0) oi
JOIN shop.orders o ON o.id = oi.order_id AND o.status = 'delivered';
