SELECT c.id, c.amount, coalesce(sum(r.amount), 0) AS refunded, c.amount - coalesce(sum(r.amount), 0) AS net
FROM payments.charges c
LEFT JOIN payments.refunds r ON r.charge_id = c.id
GROUP BY c.id, c.amount
ORDER BY c.id;
