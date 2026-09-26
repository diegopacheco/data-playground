DELETE FROM payments.charges WHERE idempotency_key LIKE 'order-%';
