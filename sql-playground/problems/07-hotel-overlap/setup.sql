CREATE EXTENSION IF NOT EXISTS btree_gist;
DROP SCHEMA IF EXISTS hotel CASCADE;
CREATE SCHEMA hotel;
COMMENT ON SCHEMA hotel IS 'Hotel reservations stored as date ranges.';
CREATE TABLE hotel.hotels (id int PRIMARY KEY, name text NOT NULL, city text NOT NULL);
CREATE TABLE hotel.room_types (id int PRIMARY KEY, name text NOT NULL, capacity int NOT NULL);
CREATE TABLE hotel.rooms (id int PRIMARY KEY, hotel_id int NOT NULL REFERENCES hotel.hotels (id), room_type_id int NOT NULL REFERENCES hotel.room_types (id), number text NOT NULL);
CREATE TABLE hotel.guests (id int PRIMARY KEY, name text NOT NULL, email text NOT NULL UNIQUE);
CREATE TABLE hotel.reservations (id bigserial PRIMARY KEY, room_id int NOT NULL REFERENCES hotel.rooms (id), guest_id int NOT NULL REFERENCES hotel.guests (id), stay daterange NOT NULL, channel text NOT NULL);
CREATE TABLE hotel.maintenance (room_id int REFERENCES hotel.rooms (id), day date, reason text NOT NULL, PRIMARY KEY (room_id, day));
COMMENT ON TABLE hotel.reservations IS 'stay is a half open daterange [check_in, check_out). No exclusion constraint so the race can show overlaps.';
COMMENT ON TABLE hotel.maintenance IS 'Days a room is blocked for repairs.';
INSERT INTO hotel.hotels VALUES (1, 'Alfama Suites', 'Lisbon'), (2, 'Ribeira Inn', 'Porto');
INSERT INTO hotel.room_types VALUES (1, 'Single', 1), (2, 'Double', 2), (3, 'Family', 4), (4, 'Penthouse', 6);
INSERT INTO hotel.rooms VALUES (1, 1, 2, '101'), (2, 1, 2, '102'), (3, 1, 3, '201'), (4, 2, 1, '11'), (5, 2, 2, '12'), (6, 2, 3, '21');
INSERT INTO hotel.guests VALUES (1, 'Beatriz Nunes', 'bea@mail.test'), (2, 'Carlos Vega', 'carlos@mail.test'), (3, 'Dana White', 'dana@mail.test'), (4, 'Emil Berg', 'emil@mail.test'), (5, 'Fatima Ali', 'fatima@mail.test');
INSERT INTO hotel.reservations (room_id, guest_id, stay, channel) VALUES
 (2, 1, daterange(current_date - 1, current_date + 2), 'direct'),
 (3, 2, daterange(current_date, current_date + 3), 'agency'),
 (4, 3, daterange(current_date - 2, current_date + 1), 'direct'),
 (5, 4, daterange(current_date + 3, current_date + 6), 'agency'),
 (2, 5, daterange(current_date + 1, current_date + 4), 'agency'),
 (6, 1, daterange(current_date - 10, current_date - 7), 'direct');
INSERT INTO hotel.maintenance VALUES (3, current_date, 'leaking shower'), (6, current_date, 'painting'), (6, current_date + 1, 'painting');
