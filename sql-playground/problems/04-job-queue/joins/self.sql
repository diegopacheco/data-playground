SELECT child.id, child.payload, parent.payload AS depends_on, parent.status AS parent_status
FROM jobs.jobs child
JOIN jobs.jobs parent ON parent.id = child.parent_id
ORDER BY child.id;
