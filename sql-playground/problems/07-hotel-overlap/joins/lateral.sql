SELECT r.number AS room, nxt.guest_id, nxt.check_in
FROM hotel.rooms r
LEFT JOIN LATERAL (
  SELECT v.guest_id, lower(v.stay) AS check_in
  FROM hotel.reservations v
  WHERE v.room_id = r.id AND lower(v.stay) >= current_date
  ORDER BY lower(v.stay)
  LIMIT 1
) nxt ON true
ORDER BY r.id;
