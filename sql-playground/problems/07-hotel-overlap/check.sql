SELECT (SELECT count(*) FROM hotel.reservations WHERE room_id = 1) AS reservations,
       count(*) AS overlapping_pairs,
       count(*) = 0 AS ok
FROM hotel.reservations a
JOIN hotel.reservations b ON a.room_id = b.room_id AND a.id < b.id AND a.stay && b.stay
WHERE a.room_id = 1;
