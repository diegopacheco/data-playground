SELECT o.name AS organization, parent.name AS parent
FROM ratelimit.orgs o
LEFT JOIN ratelimit.orgs parent ON parent.id = o.parent_id
ORDER BY parent.name NULLS FIRST, o.name;
