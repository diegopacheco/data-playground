DELETE FROM social.post_views WHERE post_id = 1;
UPDATE social.posts SET views = 0 WHERE id = 1;
