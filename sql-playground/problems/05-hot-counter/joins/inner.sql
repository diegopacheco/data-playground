SELECT u.handle, p.body, h.tag
FROM social.posts p
INNER JOIN social.users u ON u.id = p.author_id
INNER JOIN social.post_hashtags ph ON ph.post_id = p.id
INNER JOIN social.hashtags h ON h.id = ph.hashtag_id
ORDER BY p.id, h.tag;
