SELECT p.name AS product, count(*) AS units, sum(x.amount) AS revenue
FROM vending.sales x
INNER JOIN vending.slots s ON s.id = x.slot_id
INNER JOIN vending.products p ON p.id = s.product_id
GROUP BY p.name
ORDER BY revenue DESC;
