SELECT s.stock AS stock_left,
       count(x.id) AS cans_sold,
       10 AS cans_loaded,
       count(x.id) = 10 AND s.stock = 0 AS ok
FROM vending.slots s
LEFT JOIN vending.sales x ON x.slot_id = s.id
WHERE s.id = 1
GROUP BY s.stock;
