DELETE FROM bank.transfers WHERE from_account <= 4 OR to_account <= 4;
UPDATE bank.accounts SET balance = 1000 WHERE id <= 4;
