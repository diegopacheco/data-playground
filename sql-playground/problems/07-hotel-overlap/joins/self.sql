SELECT a.room_id, a.id AS first_reservation, b.id AS second_reservation, a.stay * b.stay AS overlap
FROM hotel.reservations a
JOIN hotel.reservations b ON b.room_id = a.room_id AND a.id < b.id AND a.stay && b.stay;
