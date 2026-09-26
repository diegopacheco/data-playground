SELECT w.hostname, e.job_id, e.finished_at
FROM jobs.executions e
RIGHT JOIN jobs.workers w ON w.id = e.worker_id
ORDER BY w.hostname, e.finished_at;
