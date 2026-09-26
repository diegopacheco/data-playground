SELECT c.id, m.name AS merchant, cu.name AS customer, c.amount, c.currency, c.status
FROM payments.charges c
INNER JOIN payments.merchants m ON m.id = c.merchant_id
INNER JOIN payments.customers cu ON cu.id = c.customer_id
ORDER BY c.created_at;
