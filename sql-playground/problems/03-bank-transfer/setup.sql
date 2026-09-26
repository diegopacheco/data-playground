DROP SCHEMA IF EXISTS bank CASCADE;
CREATE SCHEMA bank;
COMMENT ON SCHEMA bank IS 'Retail bank ledger with accounts and transfers.';
CREATE TABLE bank.branches (id int PRIMARY KEY, name text NOT NULL, city text NOT NULL);
CREATE TABLE bank.currencies (code char(3) PRIMARY KEY, name text NOT NULL);
CREATE TABLE bank.owners (id int PRIMARY KEY, name text NOT NULL, document text NOT NULL UNIQUE);
CREATE TABLE bank.accounts (id int PRIMARY KEY, owner_id int NOT NULL REFERENCES bank.owners (id), branch_id int NOT NULL REFERENCES bank.branches (id), currency char(3) NOT NULL REFERENCES bank.currencies (code), balance numeric(14,2) NOT NULL);
CREATE TABLE bank.transfers (id bigserial PRIMARY KEY, from_account int NOT NULL REFERENCES bank.accounts (id), to_account int NOT NULL REFERENCES bank.accounts (id), amount numeric(14,2) NOT NULL CHECK (amount > 0), created_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE bank.cards (id int PRIMARY KEY, account_id int NOT NULL REFERENCES bank.accounts (id), last4 char(4) NOT NULL, kind text NOT NULL);
CREATE TABLE bank.employees (id int PRIMARY KEY, name text NOT NULL, branch_id int REFERENCES bank.branches (id), manager_id int REFERENCES bank.employees (id));
CREATE TABLE bank.kyc_checks (document text PRIMARY KEY, result text NOT NULL, checked_on date NOT NULL);
COMMENT ON TABLE bank.accounts IS 'Balances. Rows 1 to 4 are the hot accounts of the race.';
COMMENT ON TABLE bank.transfers IS 'Money moved between two accounts.';
COMMENT ON TABLE bank.kyc_checks IS 'Know your customer file from an external vendor, joined by document.';
COMMENT ON TABLE bank.employees IS 'Branch staff. manager_id points to another employee.';
INSERT INTO bank.branches VALUES (1, 'Downtown', 'Sao Paulo'), (2, 'Harbour', 'Santos'), (3, 'Airport', 'Campinas'), (4, 'Riverside', 'Curitiba');
INSERT INTO bank.currencies VALUES ('BRL', 'Brazilian real'), ('USD', 'US dollar'), ('EUR', 'Euro');
INSERT INTO bank.owners VALUES (1, 'Marina Lima', '111'), (2, 'Otavio Reis', '222'), (3, 'Paula Dias', '333'), (4, 'Rafael Gomes', '444'), (5, 'Sofia Rocha', '555'), (6, 'Thiago Luz', '666');
INSERT INTO bank.accounts VALUES
 (1, 1, 1, 'BRL', 1000), (2, 2, 1, 'BRL', 1000), (3, 3, 2, 'BRL', 1000), (4, 4, 2, 'BRL', 1000),
 (5, 5, 1, 'USD', 8200), (6, 5, 3, 'EUR', 450), (7, 6, 3, 'BRL', 12000), (8, 1, 2, 'USD', 300);
INSERT INTO bank.transfers (from_account, to_account, amount, created_at) VALUES
 (5, 6, 200, now() - interval '9 days'), (7, 5, 1500, now() - interval '8 days'), (5, 8, 90, now() - interval '6 days'),
 (7, 6, 40, now() - interval '5 days'), (7, 8, 3000, now() - interval '3 days'), (6, 5, 25, now() - interval '1 day');
INSERT INTO bank.cards VALUES (1, 5, '4421', 'debit'), (2, 5, '9910', 'credit'), (3, 7, '1204', 'debit'), (4, 1, '7788', 'debit');
INSERT INTO bank.employees VALUES (1, 'Helena Prado', 1, NULL), (2, 'Igor Sales', 1, 1), (3, 'Julia Paz', 2, 1), (4, 'Kleber Cruz', 2, 3), (5, 'Laura Brito', 3, 3);
INSERT INTO bank.kyc_checks VALUES ('111', 'approved', '2025-01-02'), ('222', 'approved', '2025-01-05'), ('555', 'review', '2025-02-11'), ('999', 'rejected', '2025-03-01');
