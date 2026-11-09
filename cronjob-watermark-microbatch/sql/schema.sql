CREATE TABLE source_events (
  id bigserial PRIMARY KEY,
  account text NOT NULL,
  amount_cents bigint NOT NULL,
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX source_events_watermark_idx ON source_events (updated_at, id);

CREATE TABLE target_java (
  id bigint PRIMARY KEY,
  account text NOT NULL,
  amount_cents bigint NOT NULL,
  updated_at timestamptz NOT NULL
);

CREATE TABLE target_python (LIKE target_java INCLUDING ALL);

CREATE TABLE watermarks (
  job text PRIMARY KEY,
  last_updated_at timestamptz NOT NULL,
  last_id bigint NOT NULL,
  advanced_at timestamptz NOT NULL
);

INSERT INTO watermarks (job, last_updated_at, last_id, advanced_at) VALUES
  ('java', '1970-01-01T00:00:00Z', 0, now()),
  ('python', '1970-01-01T00:00:00Z', 0, now());

CREATE TABLE batch_runs (
  id bigserial PRIMARY KEY,
  job text NOT NULL,
  runner text NOT NULL,
  started_at timestamptz NOT NULL,
  duration_ms bigint NOT NULL,
  rows_loaded bigint NOT NULL,
  pages integer NOT NULL,
  last_updated_at timestamptz NOT NULL,
  last_id bigint NOT NULL
);
