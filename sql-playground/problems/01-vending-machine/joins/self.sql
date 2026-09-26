SELECT t.name AS technician, boss.name AS supervisor
FROM vending.technicians t
LEFT JOIN vending.technicians boss ON boss.id = t.supervisor_id
ORDER BY boss.name NULLS FIRST, t.name;
