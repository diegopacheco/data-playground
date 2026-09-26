DROP SCHEMA IF EXISTS jobs CASCADE;
CREATE SCHEMA jobs;
COMMENT ON SCHEMA jobs IS 'Background job queue stored in Postgres.';
CREATE TABLE jobs.queues (id int PRIMARY KEY, name text NOT NULL UNIQUE);
CREATE TABLE jobs.workers (id int PRIMARY KEY, hostname text NOT NULL UNIQUE, started_at timestamptz NOT NULL);
CREATE TABLE jobs.jobs (id bigserial PRIMARY KEY, queue_id int NOT NULL REFERENCES jobs.queues (id), parent_id bigint REFERENCES jobs.jobs (id), payload text NOT NULL, priority int NOT NULL DEFAULT 2, status text NOT NULL CHECK (status IN ('queued', 'running', 'done', 'failed')), created_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE jobs.executions (id bigserial PRIMARY KEY, job_id bigint NOT NULL REFERENCES jobs.jobs (id), worker_id int REFERENCES jobs.workers (id), backend_pid int NOT NULL DEFAULT pg_backend_pid(), finished_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE jobs.heartbeats (hostname text PRIMARY KEY, seen_at timestamptz NOT NULL);
CREATE INDEX jobs_queued_idx ON jobs.jobs (queue_id, id) WHERE status = 'queued';
COMMENT ON TABLE jobs.jobs IS 'The queue. status flips queued -> done. parent_id makes a job wait for another job.';
COMMENT ON TABLE jobs.executions IS 'One row every time a worker runs a job. More than one row per job means duplicate work.';
COMMENT ON TABLE jobs.heartbeats IS 'Last ping by hostname, written by an agent outside the registry.';
INSERT INTO jobs.queues VALUES (1, 'emails'), (2, 'invoices'), (3, 'race'), (4, 'reports');
INSERT INTO jobs.workers VALUES (1, 'worker-a', now() - interval '3 days'), (2, 'worker-b', now() - interval '3 days'), (3, 'worker-c', now() - interval '1 day'), (4, 'worker-d', now() - interval '2 hours');
INSERT INTO jobs.jobs (id, queue_id, parent_id, payload, priority, status, created_at) VALUES
 (1, 1, NULL, 'welcome ana', 1, 'done', now() - interval '5 hours'),
 (2, 1, NULL, 'welcome bia', 2, 'done', now() - interval '4 hours'),
 (3, 2, NULL, 'invoice 1001', 1, 'done', now() - interval '4 hours'),
 (4, 2, 3, 'email invoice 1001', 2, 'failed', now() - interval '3 hours'),
 (5, 2, NULL, 'invoice 1002', 1, 'queued', now() - interval '2 hours'),
 (6, 2, 5, 'email invoice 1002', 3, 'queued', now() - interval '2 hours'),
 (7, 1, NULL, 'welcome caio', 2, 'queued', now() - interval '1 hour'),
 (8, 1, NULL, 'newsletter', 3, 'failed', now() - interval '50 minutes');
SELECT setval('jobs.jobs_id_seq', 100);
INSERT INTO jobs.executions (job_id, worker_id, backend_pid, finished_at) VALUES
 (1, 1, 101, now() - interval '290 minutes'), (2, 2, 102, now() - interval '230 minutes'), (3, 1, 101, now() - interval '220 minutes'),
 (4, 2, 102, now() - interval '170 minutes'), (4, 1, 101, now() - interval '160 minutes'), (8, 3, 103, now() - interval '40 minutes');
INSERT INTO jobs.heartbeats VALUES ('worker-a', now() - interval '10 seconds'), ('worker-b', now() - interval '12 seconds'), ('worker-c', now() - interval '2 hours'), ('worker-zombie', now() - interval '5 seconds');
