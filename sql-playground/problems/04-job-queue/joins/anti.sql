SELECT j.id, j.payload, j.status
FROM jobs.jobs j
WHERE NOT EXISTS (SELECT 1 FROM jobs.executions e WHERE e.job_id = j.id)
ORDER BY j.id;
