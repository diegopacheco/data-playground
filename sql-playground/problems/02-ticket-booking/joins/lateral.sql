SELECT c.name, latest.title, latest.booked_at
FROM tickets.customers c
CROSS JOIN LATERAL (
  SELECT e.title, b.booked_at
  FROM tickets.bookings b
  JOIN tickets.events e ON e.id = b.event_id
  WHERE b.customer_id = c.id
  ORDER BY b.booked_at DESC
  LIMIT 1
) latest
ORDER BY latest.booked_at DESC;
