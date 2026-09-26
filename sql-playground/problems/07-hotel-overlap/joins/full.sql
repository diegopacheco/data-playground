SELECT coalesce(v.room_id, m.room_id) AS room_id, v.id AS reservation_id, m.reason,
       CASE WHEN v.id IS NOT NULL AND m.room_id IS NOT NULL THEN 'conflict' WHEN v.id IS NOT NULL THEN 'occupied' ELSE 'maintenance only' END AS state
FROM (SELECT * FROM hotel.reservations WHERE stay @> current_date) v
FULL OUTER JOIN (SELECT * FROM hotel.maintenance WHERE day = current_date) m ON m.room_id = v.room_id
ORDER BY room_id;
