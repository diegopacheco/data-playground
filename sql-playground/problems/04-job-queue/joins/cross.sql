SELECT q.name AS queue, p.priority, count(j.id) AS jobs
FROM jobs.queues q
CROSS JOIN generate_series(1, 3) AS p (priority)
LEFT JOIN jobs.jobs j ON j.queue_id = q.id AND j.priority = p.priority
GROUP BY q.name, p.priority
ORDER BY q.name, p.priority;
