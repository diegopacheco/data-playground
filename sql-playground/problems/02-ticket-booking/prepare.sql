DELETE FROM tickets.bookings WHERE event_id = 1;
UPDATE tickets.event_seats SET status = 'free' WHERE event_id = 1;
