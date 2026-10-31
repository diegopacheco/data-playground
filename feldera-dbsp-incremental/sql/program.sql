CREATE TABLE orders (
    id BIGINT NOT NULL PRIMARY KEY,
    customer INT NOT NULL,
    region VARCHAR NOT NULL,
    amount BIGINT NOT NULL,
    ts TIMESTAMP NOT NULL
);

CREATE TABLE edges (
    src INT NOT NULL,
    dst INT NOT NULL,
    PRIMARY KEY (src, dst)
);

CREATE MATERIALIZED VIEW region_totals AS
SELECT region, COUNT(*) AS orders, SUM(amount) AS revenue
FROM orders
GROUP BY region;

CREATE MATERIALIZED VIEW hourly_revenue AS
SELECT window_start, region, COUNT(*) AS orders, SUM(amount) AS revenue
FROM TABLE(TUMBLE(TABLE orders, DESCRIPTOR(ts), INTERVAL '1' HOUR))
GROUP BY window_start, region;

DECLARE RECURSIVE VIEW reachable (src INT NOT NULL, dst INT NOT NULL);

CREATE LOCAL VIEW hop AS
SELECT e.src, r.dst
FROM edges e
JOIN reachable r ON e.dst = r.src;

CREATE MATERIALIZED VIEW reachable AS
(SELECT src, dst FROM edges)
UNION
(SELECT src, dst FROM hop);
