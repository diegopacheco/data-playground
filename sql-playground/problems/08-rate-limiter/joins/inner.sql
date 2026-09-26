SELECT r.requested_at, o.name AS org, k.label AS api_key, p.name AS plan, r.path, r.status
FROM ratelimit.requests r
INNER JOIN ratelimit.api_keys k ON k.id = r.api_key_id
INNER JOIN ratelimit.orgs o ON o.id = k.org_id
INNER JOIN ratelimit.plans p ON p.id = k.plan_id
ORDER BY r.requested_at;
