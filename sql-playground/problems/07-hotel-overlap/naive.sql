DO $$
DECLARE
  v_start date := current_date + floor(random() * 9)::int;
  v_stay daterange;
BEGIN
  v_stay := daterange(v_start, v_start + 2);
  IF NOT EXISTS (SELECT 1 FROM hotel.reservations WHERE room_id = 1 AND stay && v_stay) THEN
    PERFORM pg_sleep(0.02);
    INSERT INTO hotel.reservations (room_id, guest_id, stay, channel) VALUES (1, 1 + floor(random() * 5)::int, v_stay, 'race');
  END IF;
END $$;
