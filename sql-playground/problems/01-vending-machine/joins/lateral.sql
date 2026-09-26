SELECT m.id AS machine_id, last.code, last.amount, last.sold_at
FROM vending.machines m
CROSS JOIN LATERAL (
  SELECT s.code, x.amount, x.sold_at
  FROM vending.slots s
  JOIN vending.sales x ON x.slot_id = s.id
  WHERE s.machine_id = m.id
  ORDER BY x.sold_at DESC
  LIMIT 2
) last
ORDER BY m.id, last.sold_at DESC;
