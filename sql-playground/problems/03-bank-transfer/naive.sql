DO $$
DECLARE
  v_from int := 1 + floor(random() * 4)::int;
  v_to int;
  v_amount int := 1 + floor(random() * 50)::int;
  v_from_balance numeric;
  v_to_balance numeric;
BEGIN
  v_to := 1 + (v_from + floor(random() * 3)::int) % 4;
  SELECT balance INTO v_from_balance FROM bank.accounts WHERE id = v_from;
  SELECT balance INTO v_to_balance FROM bank.accounts WHERE id = v_to;
  PERFORM pg_sleep(0.01);
  IF v_from_balance >= v_amount THEN
    UPDATE bank.accounts SET balance = v_from_balance - v_amount WHERE id = v_from;
    UPDATE bank.accounts SET balance = v_to_balance + v_amount WHERE id = v_to;
    INSERT INTO bank.transfers (from_account, to_account, amount) VALUES (v_from, v_to, v_amount);
  END IF;
END $$;
