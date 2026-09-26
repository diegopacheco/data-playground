CREATE MATERIALIZED VIEW mv_revenue_by_category AS
SELECT category AS mv_category, count(order_id) AS mv_orders, sum(quantity) AS mv_quantity,
       sum(quantity * price) AS mv_revenue
FROM sales.orders
GROUP BY category;
