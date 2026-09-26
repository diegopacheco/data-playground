SELECT u.handle, count(p.id) AS posts
FROM social.users u
LEFT JOIN social.posts p ON p.author_id = u.id
GROUP BY u.handle
ORDER BY posts DESC, u.handle;
