SELECT c.id, c.name
FROM tickets.customers c
WHERE EXISTS (
  SELECT 1
  FROM tickets.bookings b
  JOIN tickets.events e ON e.id = b.event_id
  JOIN tickets.venues v ON v.id = e.venue_id
  WHERE b.customer_id = c.id AND v.city = 'Lisbon'
)
ORDER BY c.id;
