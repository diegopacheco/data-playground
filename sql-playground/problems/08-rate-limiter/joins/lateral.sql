SELECT k.label, last.path, last.status, last.requested_at
FROM ratelimit.api_keys k
CROSS JOIN LATERAL (
  SELECT r.path, r.status, r.requested_at
  FROM ratelimit.requests r
  WHERE r.api_key_id = k.id
  ORDER BY r.requested_at DESC
  LIMIT 2
) last
ORDER BY k.label, last.requested_at DESC;
