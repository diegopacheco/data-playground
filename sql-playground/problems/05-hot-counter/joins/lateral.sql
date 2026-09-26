SELECT u.handle, top.body, top.views
FROM social.users u
LEFT JOIN LATERAL (
  SELECT p.body, p.views
  FROM social.posts p
  WHERE p.author_id = u.id
  ORDER BY p.views DESC
  LIMIT 1
) top ON true
ORDER BY top.views DESC NULLS LAST, u.handle;
