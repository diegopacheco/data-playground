DO $$
DECLARE
  v_stock int;
BEGIN
  SELECT stock INTO v_stock FROM vending.slots WHERE id = 1;
  PERFORM pg_sleep(0.02);
  IF v_stock > 0 THEN
    UPDATE vending.slots SET stock = v_stock - 1 WHERE id = 1;
    INSERT INTO vending.sales (slot_id, amount) VALUES (1, 1.80);
  END IF;
END $$;
