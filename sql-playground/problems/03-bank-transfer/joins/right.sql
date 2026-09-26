SELECT b.name AS branch, a.id AS account_id, a.balance
FROM bank.accounts a
RIGHT JOIN bank.branches b ON b.id = a.branch_id
ORDER BY b.name, a.id;
