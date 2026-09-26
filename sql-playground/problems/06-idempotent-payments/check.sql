SELECT k.key AS idempotency_key,
       count(c.id) AS charges,
       count(c.id) = 1 AS ok
FROM (SELECT 'order-' || g AS key FROM generate_series(1, 5) g) k
LEFT JOIN payments.charges c ON c.merchant_id = 1 AND c.idempotency_key = k.key
GROUP BY k.key
ORDER BY k.key;
