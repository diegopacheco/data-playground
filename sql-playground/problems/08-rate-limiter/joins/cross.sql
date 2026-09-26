SELECT k.label, m.minute, count(r.id) AS requests
FROM ratelimit.api_keys k
CROSS JOIN generate_series(date_trunc('minute', now()) - interval '4 minutes', date_trunc('minute', now()), interval '1 minute') AS m (minute)
LEFT JOIN ratelimit.requests r ON r.api_key_id = k.id AND r.requested_at >= m.minute AND r.requested_at < m.minute + interval '1 minute'
GROUP BY k.label, m.minute
ORDER BY k.label, m.minute;
