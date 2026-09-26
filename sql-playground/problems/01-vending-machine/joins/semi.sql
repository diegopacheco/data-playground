SELECT m.id, m.model
FROM vending.machines m
WHERE EXISTS (SELECT 1 FROM vending.slots s WHERE s.machine_id = m.id AND s.stock = 0)
ORDER BY m.id;
