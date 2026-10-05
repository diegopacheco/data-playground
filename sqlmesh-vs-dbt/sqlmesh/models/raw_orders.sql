MODEL (
  name raw.orders,
  kind SEED (
    path '../../data/orders.csv'
  ),
  columns (
    order_id INT,
    customer TEXT,
    product TEXT,
    category TEXT,
    quantity INT,
    price DECIMAL(10, 2),
    ts TEXT
  ),
  grain order_id
);
