DO $$
BEGIN
  PERFORM pg_sleep(0.01);
  UPDATE social.posts SET views = views + 1 WHERE id = 1;
  INSERT INTO social.post_views (post_id) VALUES (1);
END $$;
