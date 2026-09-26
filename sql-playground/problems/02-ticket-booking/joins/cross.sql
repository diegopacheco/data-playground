SELECT e.title, sec.section,
       (SELECT count(*) FROM tickets.bookings b JOIN tickets.seats s ON s.id = b.seat_id
        WHERE b.event_id = e.id AND s.section = sec.section) AS sold
FROM tickets.events e
CROSS JOIN (SELECT DISTINCT section FROM tickets.seats) sec
ORDER BY e.title, sec.section;
