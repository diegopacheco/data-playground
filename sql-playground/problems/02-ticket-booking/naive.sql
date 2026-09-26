DO $$
DECLARE
  v_seat int;
BEGIN
  SELECT es.seat_id INTO v_seat
  FROM tickets.event_seats es
  JOIN tickets.seats s ON s.id = es.seat_id
  WHERE es.event_id = 1 AND es.status = 'free' AND s.section = 'VIP'
  ORDER BY es.seat_id
  LIMIT 1;
  PERFORM pg_sleep(0.02);
  IF v_seat IS NOT NULL THEN
    UPDATE tickets.event_seats SET status = 'sold' WHERE event_id = 1 AND seat_id = v_seat;
    INSERT INTO tickets.bookings (event_id, seat_id, customer_id) VALUES (1, v_seat, 1 + floor(random() * 30)::int);
  END IF;
END $$;
