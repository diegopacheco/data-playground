SELECT g.id, g.name
FROM hotel.guests g
WHERE EXISTS (
  SELECT 1 FROM hotel.reservations v
  JOIN hotel.rooms r ON r.id = v.room_id
  JOIN hotel.hotels h ON h.id = r.hotel_id
  WHERE v.guest_id = g.id AND h.city = 'Lisbon'
)
ORDER BY g.id;
