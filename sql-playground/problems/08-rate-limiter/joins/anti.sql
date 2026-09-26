SELECT k.id, k.label
FROM ratelimit.api_keys k
LEFT JOIN ratelimit.requests r ON r.api_key_id = k.id
WHERE r.id IS NULL;
