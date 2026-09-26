SELECT m.id AS machine_id, p.name AS product,
       EXISTS (SELECT 1 FROM vending.slots s WHERE s.machine_id = m.id AND s.product_id = p.id) AS stocked
FROM vending.machines m
CROSS JOIN vending.products p
ORDER BY m.id, p.id;
