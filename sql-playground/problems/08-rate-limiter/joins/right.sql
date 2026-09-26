SELECT p.name AS plan, p.limit_per_minute, k.label AS api_key
FROM ratelimit.api_keys k
RIGHT JOIN ratelimit.plans p ON p.id = k.plan_id
ORDER BY p.id, k.label;
