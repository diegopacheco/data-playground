DO $$
DECLARE
  v_used int;
BEGIN
  SELECT count(*) INTO v_used FROM ratelimit.requests
  WHERE api_key_id = 1 AND status = 200 AND requested_at > clock_timestamp() - interval '1 minute';
  PERFORM pg_sleep(0.02);
  IF v_used < 10 THEN
    INSERT INTO ratelimit.requests (api_key_id, path, status) VALUES (1, '/v1/search', 200);
  ELSE
    INSERT INTO ratelimit.requests (api_key_id, path, status) VALUES (1, '/v1/search', 429);
  END IF;
END $$;
