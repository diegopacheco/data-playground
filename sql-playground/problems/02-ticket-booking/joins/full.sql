SELECT c.name AS customer, coalesce(c.email, n.email) AS email,
       CASE WHEN n.email IS NULL THEN 'customer only' WHEN c.id IS NULL THEN 'subscriber only' ELSE 'both' END AS match
FROM tickets.customers c
FULL OUTER JOIN tickets.newsletter n ON n.email = c.email
WHERE c.id <= 6 OR c.id IS NULL
ORDER BY match, email;
