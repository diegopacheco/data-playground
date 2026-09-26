SELECT m.name AS merchant, cur.code AS currency, coalesce(sum(c.amount), 0) AS captured
FROM payments.merchants m
CROSS JOIN (VALUES ('BRL'), ('USD'), ('EUR')) AS cur (code)
LEFT JOIN payments.charges c ON c.merchant_id = m.id AND c.currency = cur.code AND c.status = 'captured'
GROUP BY m.name, cur.code
ORDER BY m.name, cur.code;
