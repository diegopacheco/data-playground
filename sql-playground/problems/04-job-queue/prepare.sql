DELETE FROM jobs.executions WHERE job_id IN (SELECT id FROM jobs.jobs WHERE queue_id = 3);
DELETE FROM jobs.jobs WHERE queue_id = 3;
INSERT INTO jobs.jobs (queue_id, payload, priority, status) SELECT 3, 'race job ' || g, 2, 'queued' FROM generate_series(1, 30) g;
