DO $$
DECLARE
  v_job bigint;
BEGIN
  SELECT id INTO v_job FROM jobs.jobs WHERE queue_id = 3 AND status = 'queued' ORDER BY id LIMIT 1;
  PERFORM pg_sleep(0.02);
  IF v_job IS NOT NULL THEN
    UPDATE jobs.jobs SET status = 'done' WHERE id = v_job;
    INSERT INTO jobs.executions (job_id) VALUES (v_job);
  END IF;
END $$;
