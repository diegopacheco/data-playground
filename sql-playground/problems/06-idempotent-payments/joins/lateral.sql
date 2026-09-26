SELECT m.name, biggest.id AS charge_id, biggest.amount, biggest.currency
FROM payments.merchants m
CROSS JOIN LATERAL (
  SELECT c.id, c.amount, c.currency
  FROM payments.charges c
  WHERE c.merchant_id = m.id
  ORDER BY c.amount DESC
  LIMIT 1
) biggest
ORDER BY biggest.amount DESC;
