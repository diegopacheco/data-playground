SELECT count(*) AS jobs,
       count(*) FILTER (WHERE runs = 1) AS ran_once,
       count(*) FILTER (WHERE runs > 1) AS ran_more_than_once,
       count(*) FILTER (WHERE runs = 0) AS never_ran,
       coalesce(sum(runs), 0) AS executions,
       count(*) FILTER (WHERE runs <> 1) = 0 AS ok
FROM (
  SELECT j.id, count(e.id) AS runs
  FROM jobs.jobs j
  LEFT JOIN jobs.executions e ON e.job_id = j.id
  WHERE j.queue_id = 3
  GROUP BY j.id
) r;
