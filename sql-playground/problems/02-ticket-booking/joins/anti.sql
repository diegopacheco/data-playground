SELECT e.id, e.title
FROM tickets.events e
LEFT JOIN tickets.bookings b ON b.event_id = e.id
WHERE b.id IS NULL;
