SELECT e.path AS documented, seen.path AS called, seen.calls,
       CASE WHEN seen.path IS NULL THEN 'never called' WHEN e.path IS NULL THEN 'undocumented' ELSE 'ok' END AS state
FROM ratelimit.endpoints e
FULL OUTER JOIN (SELECT path, count(*) AS calls FROM ratelimit.requests GROUP BY path) seen ON seen.path = e.path
ORDER BY state, coalesce(e.path, seen.path);
