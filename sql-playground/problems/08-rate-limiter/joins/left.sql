SELECT k.label, count(r.id) AS requests_last_day
FROM ratelimit.api_keys k
LEFT JOIN ratelimit.requests r ON r.api_key_id = k.id AND r.requested_at > now() - interval '1 day'
GROUP BY k.label
ORDER BY requests_last_day DESC, k.label;
