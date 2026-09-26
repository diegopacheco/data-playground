DO $$
DECLARE
  v_key text := 'order-' || (1 + floor(random() * 5)::int);
  v_id bigint;
BEGIN
  INSERT INTO payments.charges (merchant_id, customer_id, idempotency_key, amount, currency, status)
  VALUES (1, 4, v_key, 49.90, 'BRL', 'captured')
  ON CONFLICT (merchant_id, idempotency_key) DO NOTHING
  RETURNING id INTO v_id;
  IF v_id IS NOT NULL THEN
    PERFORM pg_sleep(0.02);
  END IF;
END $$;
