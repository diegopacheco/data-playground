SELECT h.tag, ph.post_id
FROM social.post_hashtags ph
RIGHT JOIN social.hashtags h ON h.id = ph.hashtag_id
ORDER BY h.tag, ph.post_id;
