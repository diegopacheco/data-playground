CREATE TABLE IF NOT EXISTS customers (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  tier TEXT NOT NULL,
  country TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS orders (
  id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  customer_id TEXT NOT NULL REFERENCES customers (id),
  customer_name TEXT NOT NULL,
  tier TEXT NOT NULL,
  sku TEXT NOT NULL,
  qty INTEGER NOT NULL,
  unit_price_cents BIGINT NOT NULL,
  total_cents BIGINT NOT NULL,
  discount_cents BIGINT NOT NULL,
  net_cents BIGINT NOT NULL,
  priority TEXT NOT NULL,
  country TEXT NOT NULL,
  email TEXT NOT NULL,
  channel TEXT NOT NULL,
  inserted_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS orders_run_id ON orders (run_id);
