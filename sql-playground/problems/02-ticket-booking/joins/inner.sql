SELECT c.name AS customer, e.title AS event, s.section, s.row_label || s.seat_number AS seat, b.booked_at
FROM tickets.bookings b
INNER JOIN tickets.customers c ON c.id = b.customer_id
INNER JOIN tickets.events e ON e.id = b.event_id
INNER JOIN tickets.seats s ON s.id = b.seat_id
ORDER BY e.title, seat;
