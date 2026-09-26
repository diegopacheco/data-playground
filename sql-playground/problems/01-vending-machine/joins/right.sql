SELECT l.name AS location, l.city, m.id AS machine_id, m.model
FROM vending.machines m
RIGHT JOIN vending.locations l ON l.id = m.location_id
ORDER BY l.name, m.id;
