SELECT p.id, p.body
FROM social.posts p
WHERE p.id NOT IN (SELECT v.post_id FROM social.post_views v)
ORDER BY p.id;
