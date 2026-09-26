SELECT m.name AS merchant, c.id AS charge_id, c.amount
FROM payments.charges c
RIGHT JOIN payments.merchants m ON m.id = c.merchant_id
ORDER BY m.name, c.id;
