SELECT count(*) FILTER (WHERE status = 200) AS accepted,
       count(*) FILTER (WHERE status = 429) AS throttled,
       10 AS limit_per_minute,
       count(*) FILTER (WHERE status = 200) <= 10 AS ok
FROM ratelimit.requests
WHERE api_key_id = 1;
