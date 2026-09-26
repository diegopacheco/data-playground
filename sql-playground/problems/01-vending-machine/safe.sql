DO $$
BEGIN
  UPDATE vending.slots SET stock = stock - 1 WHERE id = 1 AND stock > 0;
  IF FOUND THEN
    PERFORM pg_sleep(0.02);
    INSERT INTO vending.sales (slot_id, amount) VALUES (1, 1.80);
  END IF;
END $$;
