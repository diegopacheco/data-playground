SELECT b.name AS branch, c.code AS currency, coalesce(sum(a.balance), 0) AS balance
FROM bank.branches b
CROSS JOIN bank.currencies c
LEFT JOIN bank.accounts a ON a.branch_id = b.id AND a.currency = c.code
GROUP BY b.name, c.code
ORDER BY b.name, c.code;
