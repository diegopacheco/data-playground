SELECT p.views AS counter,
       (SELECT count(*) FROM social.post_views v WHERE v.post_id = p.id) AS events,
       p.views = (SELECT count(*) FROM social.post_views v WHERE v.post_id = p.id) AS ok
FROM social.posts p
WHERE p.id = 1;
