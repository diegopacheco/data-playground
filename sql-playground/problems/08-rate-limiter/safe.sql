DO $$
DECLARE
  v_limit int;
  v_used int;
BEGIN
  SELECT p.limit_per_minute INTO v_limit
  FROM ratelimit.api_keys k JOIN ratelimit.plans p ON p.id = k.plan_id
  WHERE k.id = 1
  FOR UPDATE OF k;
  SELECT count(*) INTO v_used FROM ratelimit.requests
  WHERE api_key_id = 1 AND status = 200 AND requested_at > clock_timestamp() - interval '1 minute';
  PERFORM pg_sleep(0.02);
  IF v_used < v_limit THEN
    INSERT INTO ratelimit.requests (api_key_id, path, status) VALUES (1, '/v1/search', 200);
  ELSE
    INSERT INTO ratelimit.requests (api_key_id, path, status) VALUES (1, '/v1/search', 429);
  END IF;
END $$;
