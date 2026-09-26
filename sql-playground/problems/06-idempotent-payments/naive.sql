DO $$
DECLARE
  v_key text := 'order-' || (1 + floor(random() * 5)::int);
BEGIN
  IF NOT EXISTS (SELECT 1 FROM payments.charges WHERE merchant_id = 1 AND idempotency_key = v_key) THEN
    PERFORM pg_sleep(0.02);
    INSERT INTO payments.charges (merchant_id, customer_id, idempotency_key, amount, currency, status)
    VALUES (1, 4, v_key, 49.90, 'BRL', 'captured');
  END IF;
END $$;
