SELECT r.id, r.number, g.name AS guest_tonight
FROM hotel.rooms r
LEFT JOIN hotel.reservations v ON v.room_id = r.id AND v.stay @> current_date
LEFT JOIN hotel.guests g ON g.id = v.guest_id
ORDER BY r.id;
