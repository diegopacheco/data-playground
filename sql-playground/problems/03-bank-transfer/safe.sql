DO $$
DECLARE
  v_from int := 1 + floor(random() * 4)::int;
  v_to int;
  v_amount int := 1 + floor(random() * 50)::int;
BEGIN
  v_to := 1 + (v_from + floor(random() * 3)::int) % 4;
  PERFORM 1 FROM bank.accounts WHERE id IN (v_from, v_to) ORDER BY id FOR UPDATE;
  PERFORM pg_sleep(0.01);
  UPDATE bank.accounts SET balance = balance - v_amount WHERE id = v_from AND balance >= v_amount;
  IF FOUND THEN
    UPDATE bank.accounts SET balance = balance + v_amount WHERE id = v_to;
    INSERT INTO bank.transfers (from_account, to_account, amount) VALUES (v_from, v_to, v_amount);
  END IF;
END $$;
