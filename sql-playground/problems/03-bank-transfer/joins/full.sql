SELECT o.name, coalesce(o.document, k.document) AS document, k.result,
       CASE WHEN k.document IS NULL THEN 'never checked' WHEN o.id IS NULL THEN 'unknown owner' ELSE 'matched' END AS status
FROM bank.owners o
FULL OUTER JOIN bank.kyc_checks k ON k.document = o.document
ORDER BY status, document;
