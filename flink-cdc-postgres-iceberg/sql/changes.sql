BEGIN;

INSERT INTO orders (order_id, customer, product, category, quantity, price, ts) VALUES
  (2001, 'Ana Lima', 'Garden Hose', 'garden', 2, 35.50, '2026-02-01 09:00:00'),
  (2002, 'Hugo Martins', 'Dune', 'books', 1, 18.90, '2026-02-01 09:30:00'),
  (2003, 'Emma Brown', 'Kite', 'toys', 4, 15.25, '2026-02-01 10:00:00');

UPDATE orders SET quantity = 5 WHERE order_id = 1001;
UPDATE orders SET category = 'home' WHERE order_id = 1004;
UPDATE orders SET price = ROUND(price * 1.10, 2) WHERE category = 'books';

DELETE FROM orders WHERE order_id IN (1003, 1006, 1007);

COMMIT;
