SELECT w.hostname, recent.job_id, recent.finished_at
FROM jobs.workers w
LEFT JOIN LATERAL (
  SELECT e.job_id, e.finished_at
  FROM jobs.executions e
  WHERE e.worker_id = w.id
  ORDER BY e.finished_at DESC
  LIMIT 2
) recent ON true
ORDER BY w.hostname, recent.finished_at DESC;
