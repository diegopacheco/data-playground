SELECT a.id AS account_id, o.name AS owner, count(c.id) AS cards
FROM bank.accounts a
JOIN bank.owners o ON o.id = a.owner_id
LEFT JOIN bank.cards c ON c.account_id = a.id
GROUP BY a.id, o.name
ORDER BY a.id;
