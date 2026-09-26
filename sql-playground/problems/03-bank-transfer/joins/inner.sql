SELECT t.id, src.name AS from_owner, dst.name AS to_owner, t.amount, t.created_at
FROM bank.transfers t
INNER JOIN bank.accounts a_from ON a_from.id = t.from_account
INNER JOIN bank.owners src ON src.id = a_from.owner_id
INNER JOIN bank.accounts a_to ON a_to.id = t.to_account
INNER JOIN bank.owners dst ON dst.id = a_to.owner_id
ORDER BY t.created_at;
