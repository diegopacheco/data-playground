SELECT u.id, u.handle
FROM social.users u
WHERE EXISTS (
  SELECT 1
  FROM social.follows f
  JOIN social.posts p ON p.author_id = f.followee_id
  WHERE f.follower_id = u.id
    AND (SELECT count(*) FROM social.post_views v WHERE v.post_id = p.id) > 2
)
ORDER BY u.id;
