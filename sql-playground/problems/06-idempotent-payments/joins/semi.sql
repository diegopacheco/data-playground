SELECT cu.id, cu.name
FROM payments.customers cu
WHERE EXISTS (
  SELECT 1 FROM payments.charges c JOIN payments.refunds r ON r.charge_id = c.id
  WHERE c.customer_id = cu.id
);
