SELECT c.id AS charge_id, c.amount, s.charge_id AS settled_charge, s.settled_amount,
       CASE WHEN s.id IS NULL THEN 'not settled' WHEN c.id IS NULL THEN 'unknown charge' WHEN s.settled_amount <> c.amount THEN 'amount mismatch' ELSE 'ok' END AS reconciliation
FROM (SELECT * FROM payments.charges WHERE status IN ('captured', 'refunded')) c
FULL OUTER JOIN payments.settlements s ON s.charge_id = c.id
ORDER BY reconciliation, coalesce(c.id, s.charge_id);
