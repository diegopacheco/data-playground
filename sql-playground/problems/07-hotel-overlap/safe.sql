DO $$
DECLARE
  v_start date := current_date + floor(random() * 9)::int;
BEGIN
  PERFORM pg_sleep(0.02);
  INSERT INTO hotel.reservations (room_id, guest_id, stay, channel) VALUES (1, 1 + floor(random() * 5)::int, daterange(v_start, v_start + 2), 'race');
EXCEPTION WHEN exclusion_violation THEN
  NULL;
END $$;
