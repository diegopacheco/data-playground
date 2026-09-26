SELECT a.id, a.balance
FROM bank.accounts a
WHERE NOT EXISTS (SELECT 1 FROM bank.transfers t WHERE t.from_account = a.id OR t.to_account = a.id);
