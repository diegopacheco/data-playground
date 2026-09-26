SELECT o.id, o.name
FROM bank.owners o
WHERE o.id IN (SELECT a.owner_id FROM bank.accounts a WHERE a.balance > 5000);
