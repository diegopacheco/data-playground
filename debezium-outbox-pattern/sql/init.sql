CREATE TABLE customers (
  customer_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  tier TEXT NOT NULL
);

CREATE TABLE orders (
  order_id TEXT PRIMARY KEY,
  customer_id TEXT NOT NULL,
  amount NUMERIC(10,2) NOT NULL CHECK (amount > 0),
  status TEXT NOT NULL,
  version INT NOT NULL
);

CREATE TABLE outbox (
  id UUID PRIMARY KEY DEFAULT uuidv7(),
  aggregatetype TEXT NOT NULL,
  aggregateid TEXT NOT NULL,
  type TEXT NOT NULL,
  payload JSONB NOT NULL
);

CREATE TABLE dual_write_orders (
  variant TEXT NOT NULL,
  order_id TEXT NOT NULL,
  amount NUMERIC(10,2) NOT NULL,
  PRIMARY KEY (variant, order_id)
);

CREATE TABLE processed_events (
  event_id UUID PRIMARY KEY,
  topic TEXT NOT NULL,
  aggregateid TEXT NOT NULL,
  type TEXT NOT NULL
);

CREATE TABLE projection (
  aggregateid TEXT PRIMARY KEY,
  last_type TEXT NOT NULL,
  applied INT NOT NULL,
  deliveries INT NOT NULL
);

CREATE TABLE facts (
  name TEXT PRIMARY KEY,
  value BIGINT NOT NULL
);
