CREATE UNIQUE INDEX charges_idempotency_key ON payments.charges (merchant_id, idempotency_key);
