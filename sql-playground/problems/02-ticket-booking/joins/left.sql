SELECT e.title, count(b.id) AS tickets_sold
FROM tickets.events e
LEFT JOIN tickets.bookings b ON b.event_id = e.id
GROUP BY e.title
ORDER BY tickets_sold DESC;
