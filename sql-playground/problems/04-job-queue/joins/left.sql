SELECT q.name, count(j.id) AS queued
FROM jobs.queues q
LEFT JOIN jobs.jobs j ON j.queue_id = q.id AND j.status = 'queued'
GROUP BY q.name
ORDER BY queued DESC, q.name;
