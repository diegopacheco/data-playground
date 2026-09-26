SELECT t.name AS room_type, r.number
FROM hotel.rooms r
RIGHT JOIN hotel.room_types t ON t.id = r.room_type_id
ORDER BY t.id, r.number;
