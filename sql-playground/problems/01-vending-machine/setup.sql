DROP SCHEMA IF EXISTS vending CASCADE;
CREATE SCHEMA vending;
COMMENT ON SCHEMA vending IS 'Connected vending machines reporting sales to a central database.';
CREATE TABLE vending.locations (id int PRIMARY KEY, name text NOT NULL, city text NOT NULL);
CREATE TABLE vending.machines (id int PRIMARY KEY, location_id int REFERENCES vending.locations (id), model text NOT NULL, installed_on date NOT NULL);
CREATE TABLE vending.products (id int PRIMARY KEY, name text NOT NULL, price numeric(6,2) NOT NULL);
CREATE TABLE vending.slots (id int PRIMARY KEY, machine_id int NOT NULL REFERENCES vending.machines (id), code text NOT NULL, product_id int REFERENCES vending.products (id), stock int NOT NULL, capacity int NOT NULL, UNIQUE (machine_id, code));
CREATE TABLE vending.sales (id bigserial PRIMARY KEY, slot_id int NOT NULL REFERENCES vending.slots (id), amount numeric(6,2) NOT NULL, sold_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE vending.technicians (id int PRIMARY KEY, name text NOT NULL, supervisor_id int REFERENCES vending.technicians (id));
CREATE TABLE vending.refills (id serial PRIMARY KEY, machine_id int NOT NULL REFERENCES vending.machines (id), technician_id int NOT NULL REFERENCES vending.technicians (id), refilled_on date NOT NULL);
COMMENT ON TABLE vending.locations IS 'Places that can host a machine.';
COMMENT ON TABLE vending.machines IS 'Physical machines. location_id is NULL while the machine sits in the warehouse.';
COMMENT ON TABLE vending.products IS 'Drinks and snacks that can be loaded in a slot.';
COMMENT ON TABLE vending.slots IS 'A spiral inside a machine holding one product. stock is the hot row under contention.';
COMMENT ON TABLE vending.sales IS 'One row per item dropped.';
COMMENT ON TABLE vending.technicians IS 'Field staff. supervisor_id points to another technician.';
COMMENT ON TABLE vending.refills IS 'Visits where a technician refilled a machine.';
INSERT INTO vending.locations VALUES (1, 'Central Station', 'Lisbon'), (2, 'Tech Park', 'Porto'), (3, 'University Hall', 'Coimbra'), (4, 'Airport Gate B', 'Faro');
INSERT INTO vending.machines VALUES (1, 1, 'Snacko 3000', '2024-02-10'), (2, 1, 'ColdBox S', '2024-05-01'), (3, 2, 'Snacko 3000', '2024-07-19'), (4, 3, 'ColdBox XL', '2025-01-15'), (5, NULL, 'ColdBox S', '2025-03-02');
INSERT INTO vending.products VALUES (1, 'Cola Can', 1.80), (2, 'Sparkling Water', 1.20), (3, 'Chocolate Bar', 2.10), (4, 'Salted Chips', 1.90), (5, 'Iced Tea', 1.70), (6, 'Protein Bar', 3.40);
INSERT INTO vending.slots VALUES
 (1, 1, 'A1', 1, 1, 10), (2, 1, 'A2', 3, 4, 10), (3, 1, 'B1', 4, 0, 8),
 (4, 2, 'A1', 1, 6, 12), (5, 2, 'A2', 2, 9, 12), (6, 2, 'B1', 5, 0, 12),
 (7, 3, 'A1', 3, 7, 10), (8, 3, 'A2', 4, 5, 10), (9, 3, 'B1', NULL, 0, 10),
 (10, 4, 'A1', 1, 11, 15), (11, 4, 'A2', 2, 3, 15), (12, 4, 'B1', 3, 8, 15);
INSERT INTO vending.sales (slot_id, amount, sold_at) VALUES
 (1, 1.80, now() - interval '5 hours'), (1, 1.80, now() - interval '3 hours'), (2, 2.10, now() - interval '170 minutes'),
 (3, 1.90, now() - interval '150 minutes'), (3, 1.90, now() - interval '140 minutes'), (4, 1.80, now() - interval '130 minutes'),
 (5, 1.20, now() - interval '120 minutes'), (5, 1.20, now() - interval '100 minutes'), (6, 1.70, now() - interval '90 minutes'),
 (7, 2.10, now() - interval '80 minutes'), (8, 1.90, now() - interval '70 minutes'), (7, 2.10, now() - interval '60 minutes'),
 (10, 1.80, now() - interval '50 minutes'), (11, 1.20, now() - interval '40 minutes'), (12, 2.10, now() - interval '30 minutes'),
 (10, 1.80, now() - interval '20 minutes'), (1, 1.80, now() - interval '10 minutes'), (4, 1.80, now() - interval '5 minutes');
INSERT INTO vending.technicians VALUES (1, 'Rita Lopes', NULL), (2, 'Tiago Alves', 1), (3, 'Sara Costa', 1), (4, 'Nuno Reis', 2), (5, 'Ines Mota', 2);
INSERT INTO vending.refills (machine_id, technician_id, refilled_on) VALUES (1, 2, current_date - 3), (2, 4, current_date - 2), (3, 4, current_date - 1), (1, 5, current_date), (4, 3, current_date - 6);
