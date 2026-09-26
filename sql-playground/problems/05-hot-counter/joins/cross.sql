SELECT p.id AS post_id, d.day::date, count(v.id) AS views
FROM social.posts p
CROSS JOIN generate_series(current_date - 2, current_date, interval '1 day') AS d (day)
LEFT JOIN social.post_views v ON v.post_id = p.id AND v.viewed_at >= d.day AND v.viewed_at < d.day + interval '1 day'
GROUP BY p.id, d.day
ORDER BY p.id, d.day;
