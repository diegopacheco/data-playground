SELECT a.id AS account_id, top.to_account, top.amount
FROM bank.accounts a
CROSS JOIN LATERAL (
  SELECT t.to_account, t.amount
  FROM bank.transfers t
  WHERE t.from_account = a.id
  ORDER BY t.amount DESC
  LIMIT 2
) top
ORDER BY a.id, top.amount DESC;
