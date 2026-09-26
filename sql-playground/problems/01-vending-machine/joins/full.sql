SELECT m.id AS machine_id, m.model, l.name AS location
FROM vending.machines m
FULL OUTER JOIN vending.locations l ON l.id = m.location_id
WHERE m.id IS NULL OR l.id IS NULL;
