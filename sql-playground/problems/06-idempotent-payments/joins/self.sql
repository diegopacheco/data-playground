SELECT sub.name AS sub_merchant, parent.name AS marketplace
FROM payments.merchants sub
JOIN payments.merchants parent ON parent.id = sub.parent_id
ORDER BY parent.name, sub.name;
