DO $$
DECLARE
  v_views bigint;
BEGIN
  SELECT views INTO v_views FROM social.posts WHERE id = 1;
  PERFORM pg_sleep(0.01);
  UPDATE social.posts SET views = v_views + 1 WHERE id = 1;
  INSERT INTO social.post_views (post_id) VALUES (1);
END $$;
