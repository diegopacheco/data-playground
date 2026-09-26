DROP SCHEMA IF EXISTS payments CASCADE;
CREATE SCHEMA payments;
COMMENT ON SCHEMA payments IS 'Payment gateway with idempotency keys and settlement files.';
CREATE TABLE payments.merchants (id int PRIMARY KEY, name text NOT NULL, parent_id int REFERENCES payments.merchants (id), country char(2) NOT NULL);
CREATE TABLE payments.customers (id int PRIMARY KEY, name text NOT NULL, email text NOT NULL UNIQUE);
CREATE TABLE payments.charges (id bigserial PRIMARY KEY, merchant_id int NOT NULL REFERENCES payments.merchants (id), customer_id int NOT NULL REFERENCES payments.customers (id), idempotency_key text, amount numeric(10,2) NOT NULL, currency char(3) NOT NULL, status text NOT NULL CHECK (status IN ('captured', 'refunded', 'failed')), created_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE payments.refunds (id serial PRIMARY KEY, charge_id bigint NOT NULL REFERENCES payments.charges (id), amount numeric(10,2) NOT NULL, created_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE payments.settlements (id serial PRIMARY KEY, charge_id bigint NOT NULL, settled_amount numeric(10,2) NOT NULL, settled_on date NOT NULL);
COMMENT ON TABLE payments.charges IS 'One row per charge. idempotency_key has no unique index so the race can show duplicates.';
COMMENT ON TABLE payments.settlements IS 'Daily file from the acquirer. charge_id is not a foreign key because the file can reference unknown charges.';
COMMENT ON TABLE payments.merchants IS 'Sellers. parent_id links a sub merchant to its marketplace.';
INSERT INTO payments.merchants VALUES (1, 'Mega Market', NULL, 'BR'), (2, 'Mega Market Books', 1, 'BR'), (3, 'Mega Market Games', 1, 'BR'), (4, 'Tokyo Tea', NULL, 'JP'), (5, 'Berlin Bikes', NULL, 'DE');
INSERT INTO payments.customers VALUES (1, 'Ana Souza', 'ana@mail.test'), (2, 'Kenji Sato', 'kenji@mail.test'), (3, 'Lena Wolf', 'lena@mail.test'), (4, 'Omar Haddad', 'omar@mail.test');
INSERT INTO payments.charges (id, merchant_id, customer_id, idempotency_key, amount, currency, status, created_at) VALUES
 (1, 1, 1, 'chk-a1', 120.00, 'BRL', 'captured', now() - interval '6 days'),
 (2, 2, 1, 'chk-a2', 45.90, 'BRL', 'refunded', now() - interval '5 days'),
 (3, 4, 2, 'chk-k1', 32.00, 'USD', 'captured', now() - interval '4 days'),
 (4, 3, 3, 'chk-l1', 299.00, 'EUR', 'captured', now() - interval '3 days'),
 (5, 4, 2, 'chk-k2', 18.50, 'USD', 'failed', now() - interval '2 days'),
 (6, 1, 3, 'chk-l2', 75.00, 'BRL', 'captured', now() - interval '1 day'),
 (7, 3, 1, 'chk-a3', 60.00, 'BRL', 'captured', now() - interval '3 hours');
SELECT setval('payments.charges_id_seq', 100);
INSERT INTO payments.refunds (charge_id, amount, created_at) VALUES (2, 45.90, now() - interval '4 days'), (4, 50.00, now() - interval '2 days');
INSERT INTO payments.settlements (charge_id, settled_amount, settled_on) VALUES (1, 120.00, current_date - 5), (3, 32.00, current_date - 3), (4, 299.00, current_date - 2), (999, 10.00, current_date - 1);
