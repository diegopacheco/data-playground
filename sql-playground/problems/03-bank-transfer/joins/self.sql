SELECT e.name AS employee, m.name AS manager
FROM bank.employees e
LEFT JOIN bank.employees m ON m.id = e.manager_id
ORDER BY m.name NULLS FIRST, e.name;
