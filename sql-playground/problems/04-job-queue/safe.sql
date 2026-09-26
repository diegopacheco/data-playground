DO $$
DECLARE
  v_job bigint;
BEGIN
  UPDATE jobs.jobs SET status = 'done'
  WHERE id = (
    SELECT id FROM jobs.jobs
    WHERE queue_id = 3 AND status = 'queued'
    ORDER BY id
    LIMIT 1
    FOR UPDATE SKIP LOCKED
  )
  RETURNING id INTO v_job;
  PERFORM pg_sleep(0.02);
  IF v_job IS NOT NULL THEN
    INSERT INTO jobs.executions (job_id) VALUES (v_job);
  END IF;
END $$;
