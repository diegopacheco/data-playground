SELECT r.id, r.number
FROM hotel.rooms r
WHERE NOT EXISTS (
  SELECT 1 FROM hotel.reservations v
  WHERE v.room_id = r.id AND v.stay && daterange(current_date, current_date + 7)
);
