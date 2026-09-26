SELECT p.name AS product, count(x.id) AS units_sold
FROM vending.products p
LEFT JOIN vending.slots s ON s.product_id = p.id
LEFT JOIN vending.sales x ON x.slot_id = s.id
GROUP BY p.name
ORDER BY units_sold DESC, p.name;
