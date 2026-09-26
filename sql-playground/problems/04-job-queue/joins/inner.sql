SELECT e.finished_at, w.hostname, q.name AS queue, j.payload
FROM jobs.executions e
INNER JOIN jobs.jobs j ON j.id = e.job_id
INNER JOIN jobs.queues q ON q.id = j.queue_id
INNER JOIN jobs.workers w ON w.id = e.worker_id
ORDER BY e.finished_at;
