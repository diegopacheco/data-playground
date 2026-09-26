DELETE FROM hotel.reservations newer
USING hotel.reservations older
WHERE newer.room_id = older.room_id AND newer.id > older.id AND newer.stay && older.stay;
ALTER TABLE hotel.reservations ADD CONSTRAINT reservations_no_overlap EXCLUDE USING gist (room_id WITH =, stay WITH &&);
