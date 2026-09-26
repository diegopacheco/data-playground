SELECT r.number AS room, d.night::date,
       EXISTS (SELECT 1 FROM hotel.reservations v WHERE v.room_id = r.id AND v.stay @> d.night::date) AS occupied
FROM hotel.rooms r
CROSS JOIN generate_series(current_date, current_date + 4, interval '1 day') AS d (night)
ORDER BY r.id, d.night;
