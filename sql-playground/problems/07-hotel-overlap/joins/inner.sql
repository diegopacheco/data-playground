SELECT h.name AS hotel, r.number AS room, g.name AS guest, lower(v.stay) AS check_in, upper(v.stay) AS check_out, v.channel
FROM hotel.reservations v
INNER JOIN hotel.guests g ON g.id = v.guest_id
INNER JOIN hotel.rooms r ON r.id = v.room_id
INNER JOIN hotel.hotels h ON h.id = r.hotel_id
ORDER BY check_in;
