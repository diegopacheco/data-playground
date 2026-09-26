DROP SCHEMA IF EXISTS tickets CASCADE;
CREATE SCHEMA tickets;
COMMENT ON SCHEMA tickets IS 'Concert ticketing with seat inventory per event.';
CREATE TABLE tickets.venues (id int PRIMARY KEY, name text NOT NULL, city text NOT NULL);
CREATE TABLE tickets.events (id int PRIMARY KEY, venue_id int NOT NULL REFERENCES tickets.venues (id), title text NOT NULL, starts_at timestamptz NOT NULL);
CREATE TABLE tickets.seats (id int PRIMARY KEY, venue_id int NOT NULL REFERENCES tickets.venues (id), section text NOT NULL, row_label text NOT NULL, seat_number int NOT NULL);
CREATE TABLE tickets.event_seats (event_id int REFERENCES tickets.events (id), seat_id int REFERENCES tickets.seats (id), status text NOT NULL CHECK (status IN ('free', 'sold')), price numeric(8,2) NOT NULL, PRIMARY KEY (event_id, seat_id));
CREATE TABLE tickets.customers (id int PRIMARY KEY, name text NOT NULL, email text NOT NULL UNIQUE, referred_by int REFERENCES tickets.customers (id));
CREATE TABLE tickets.bookings (id bigserial PRIMARY KEY, event_id int NOT NULL, seat_id int NOT NULL, customer_id int NOT NULL REFERENCES tickets.customers (id), booked_at timestamptz NOT NULL DEFAULT now(), FOREIGN KEY (event_id, seat_id) REFERENCES tickets.event_seats (event_id, seat_id));
CREATE TABLE tickets.newsletter (email text PRIMARY KEY, subscribed_on date NOT NULL);
COMMENT ON TABLE tickets.venues IS 'Concert halls.';
COMMENT ON TABLE tickets.events IS 'Shows on sale.';
COMMENT ON TABLE tickets.seats IS 'Physical seats of a venue.';
COMMENT ON TABLE tickets.event_seats IS 'Inventory: one row per seat per event. status is the contended column.';
COMMENT ON TABLE tickets.customers IS 'Fans with an account. referred_by points to another customer.';
COMMENT ON TABLE tickets.bookings IS 'Seats bought. No unique constraint on (event_id, seat_id) so the race can show double booking.';
COMMENT ON TABLE tickets.newsletter IS 'Emails imported from the marketing tool, not linked by foreign key.';
INSERT INTO tickets.venues VALUES (1, 'Coliseu', 'Lisbon'), (2, 'Super Bock Arena', 'Porto'), (3, 'Teatro Circo', 'Braga');
INSERT INTO tickets.events VALUES
 (1, 1, 'Midnight Echoes', now() + interval '10 days'),
 (2, 1, 'Jazz on the Tagus', now() + interval '20 days'),
 (3, 2, 'Rock Harbour', now() + interval '15 days'),
 (4, 3, 'Chamber Strings', now() + interval '40 days');
INSERT INTO tickets.seats (id, venue_id, section, row_label, seat_number)
SELECT row_number() OVER (ORDER BY v, s.o, rr.r, n), v, s.sec, rr.r, n
FROM generate_series(1, 3) v
CROSS JOIN (VALUES (1, 'VIP'), (2, 'Floor'), (3, 'Balcony')) s (o, sec)
CROSS JOIN (VALUES ('A'), ('B')) rr (r)
CROSS JOIN generate_series(1, 4) n;
INSERT INTO tickets.event_seats (event_id, seat_id, status, price)
SELECT e.id, s.id, 'free', CASE s.section WHEN 'VIP' THEN 180 WHEN 'Floor' THEN 90 ELSE 55 END
FROM tickets.events e JOIN tickets.seats s ON s.venue_id = e.venue_id;
INSERT INTO tickets.customers VALUES
 (1, 'Alice Martins', 'alice@mail.test', NULL), (2, 'Bruno Faria', 'bruno@mail.test', 1), (3, 'Clara Sousa', 'clara@mail.test', 1),
 (4, 'Duarte Pinto', 'duarte@mail.test', 2), (5, 'Eva Ramos', 'eva@mail.test', NULL), (6, 'Filipa Neves', 'filipa@mail.test', 5);
INSERT INTO tickets.customers SELECT g, 'Fan ' || g, 'fan' || g || '@mail.test', 1 + g % 6 FROM generate_series(7, 30) g;
INSERT INTO tickets.newsletter VALUES ('alice@mail.test', '2025-01-10'), ('clara@mail.test', '2025-02-01'), ('eva@mail.test', '2025-03-15'), ('ghost@mail.test', '2025-04-01'), ('zoe@mail.test', '2025-05-20');
WITH b (event_id, seat_id, customer_id, ago) AS (
  VALUES (1, 9, 1, 30), (1, 10, 2, 25), (2, 1, 3, 20), (2, 2, 3, 19), (2, 13, 4, 15), (3, 25, 5, 10), (3, 26, 1, 5), (3, 33, 6, 2)
)
INSERT INTO tickets.bookings (event_id, seat_id, customer_id, booked_at)
SELECT event_id, seat_id, customer_id, now() - ago * interval '1 hour' FROM b;
UPDATE tickets.event_seats es SET status = 'sold' FROM tickets.bookings b WHERE b.event_id = es.event_id AND b.seat_id = es.seat_id;
