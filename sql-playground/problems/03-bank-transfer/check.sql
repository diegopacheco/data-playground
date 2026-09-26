SELECT sum(balance) AS total_balance,
       4000 AS expected_total,
       min(balance) AS lowest_balance,
       (SELECT count(*) FROM bank.transfers WHERE from_account <= 4) AS transfers,
       sum(balance) = 4000 AND min(balance) >= 0 AS ok
FROM bank.accounts
WHERE id <= 4;
