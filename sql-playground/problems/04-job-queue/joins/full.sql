SELECT w.hostname AS registered, h.hostname AS heartbeat, h.seen_at,
       CASE WHEN h.hostname IS NULL THEN 'silent' WHEN w.id IS NULL THEN 'unknown host' WHEN h.seen_at < now() - interval '1 minute' THEN 'stale' ELSE 'alive' END AS state
FROM jobs.workers w
FULL OUTER JOIN jobs.heartbeats h ON h.hostname = w.hostname
ORDER BY state, coalesce(w.hostname, h.hostname);
