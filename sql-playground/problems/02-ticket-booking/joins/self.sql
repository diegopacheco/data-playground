SELECT c.name AS customer, r.name AS referred_by
FROM tickets.customers c
JOIN tickets.customers r ON r.id = c.referred_by
ORDER BY r.name, c.name;
