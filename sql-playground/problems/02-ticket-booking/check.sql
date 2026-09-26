SELECT count(*) AS bookings,
       count(DISTINCT seat_id) AS distinct_seats,
       8 AS vip_seats,
       count(*) = 8 AND count(DISTINCT seat_id) = 8 AS ok
FROM tickets.bookings
WHERE event_id = 1;
