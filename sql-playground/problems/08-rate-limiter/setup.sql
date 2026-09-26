DROP SCHEMA IF EXISTS ratelimit CASCADE;
CREATE SCHEMA ratelimit;
COMMENT ON SCHEMA ratelimit IS 'API gateway with plans, keys and a request log.';
CREATE TABLE ratelimit.plans (id int PRIMARY KEY, name text NOT NULL, limit_per_minute int NOT NULL);
CREATE TABLE ratelimit.orgs (id int PRIMARY KEY, name text NOT NULL, parent_id int REFERENCES ratelimit.orgs (id));
CREATE TABLE ratelimit.api_keys (id int PRIMARY KEY, org_id int NOT NULL REFERENCES ratelimit.orgs (id), plan_id int NOT NULL REFERENCES ratelimit.plans (id), label text NOT NULL, created_at timestamptz NOT NULL);
CREATE TABLE ratelimit.requests (id bigserial PRIMARY KEY, api_key_id int NOT NULL REFERENCES ratelimit.api_keys (id), path text NOT NULL, status int NOT NULL, requested_at timestamptz NOT NULL DEFAULT clock_timestamp());
CREATE TABLE ratelimit.endpoints (path text PRIMARY KEY, method text NOT NULL, description text NOT NULL);
CREATE INDEX requests_key_time_idx ON ratelimit.requests (api_key_id, requested_at);
COMMENT ON TABLE ratelimit.requests IS 'Accepted and throttled calls. status 429 means throttled.';
COMMENT ON TABLE ratelimit.endpoints IS 'Documented API catalog, joined to requests by path text.';
COMMENT ON TABLE ratelimit.orgs IS 'Customer organizations. parent_id links a team to its company.';
INSERT INTO ratelimit.plans VALUES (1, 'Free', 10), (2, 'Pro', 600), (3, 'Enterprise', 6000), (4, 'Legacy', 30);
INSERT INTO ratelimit.orgs VALUES (1, 'Acme Corp', NULL), (2, 'Acme Payments Team', 1), (3, 'Acme Search Team', 1), (4, 'Globex', NULL), (5, 'Solo Dev', NULL);
INSERT INTO ratelimit.api_keys VALUES
 (1, 5, 1, 'solo-free', now() - interval '30 days'), (2, 2, 2, 'acme-payments', now() - interval '90 days'),
 (3, 3, 2, 'acme-search', now() - interval '60 days'), (4, 4, 3, 'globex-prod', now() - interval '20 days'), (5, 4, 3, 'globex-staging', now() - interval '2 days');
INSERT INTO ratelimit.endpoints VALUES ('/v1/search', 'GET', 'Full text search'), ('/v1/charges', 'POST', 'Create a charge'), ('/v1/users', 'GET', 'List users'), ('/v1/reports', 'GET', 'Export reports');
INSERT INTO ratelimit.requests (api_key_id, path, status, requested_at) VALUES
 (2, '/v1/charges', 200, now() - interval '4 minutes'), (2, '/v1/charges', 200, now() - interval '3 minutes'),
 (3, '/v1/search', 200, now() - interval '3 minutes'), (3, '/v1/search', 429, now() - interval '2 minutes'),
 (4, '/v1/users', 200, now() - interval '2 minutes'), (4, '/v1/internal/debug', 200, now() - interval '1 minute'),
 (2, '/v1/charges', 200, now() - interval '30 seconds'), (4, '/v1/users', 200, now() - interval '10 seconds');
