SELECT es.seat_id, es.status, c.name AS holder
FROM tickets.bookings b
JOIN tickets.customers c ON c.id = b.customer_id
RIGHT JOIN tickets.event_seats es ON es.event_id = b.event_id AND es.seat_id = b.seat_id
WHERE es.event_id = 2
ORDER BY es.seat_id;
