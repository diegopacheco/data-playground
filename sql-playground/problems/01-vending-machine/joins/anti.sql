SELECT p.id, p.name
FROM vending.products p
WHERE NOT EXISTS (
  SELECT 1
  FROM vending.slots s
  JOIN vending.sales x ON x.slot_id = s.id
  WHERE s.product_id = p.id
);
