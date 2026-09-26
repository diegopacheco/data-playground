CREATE TABLE IF NOT EXISTS revenue_by_category (
  category text PRIMARY KEY,
  total_orders bigint NOT NULL,
  total_quantity bigint NOT NULL,
  total_revenue numeric(12, 2) NOT NULL
);
