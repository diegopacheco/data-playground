SELECT c.id, c.amount, c.created_at
FROM payments.charges c
WHERE c.status = 'captured'
  AND NOT EXISTS (SELECT 1 FROM payments.settlements s WHERE s.charge_id = c.id)
ORDER BY c.id;
