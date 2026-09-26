SELECT o.id, o.name
FROM ratelimit.orgs o
WHERE EXISTS (
  SELECT 1 FROM ratelimit.api_keys k JOIN ratelimit.requests r ON r.api_key_id = k.id
  WHERE k.org_id = o.id AND r.status = 429
);
