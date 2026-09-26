SELECT q.id, q.name
FROM jobs.queues q
WHERE EXISTS (SELECT 1 FROM jobs.jobs j WHERE j.queue_id = q.id AND j.status = 'failed');
