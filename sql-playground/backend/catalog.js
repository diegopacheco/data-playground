const userSchemas = "n.nspname NOT IN ('pg_catalog', 'information_schema', 'playground', 'public') AND n.nspname NOT LIKE 'pg\\_%'"

const schemasSql = `
SELECT n.nspname AS name, obj_description(n.oid, 'pg_namespace') AS comment
FROM pg_namespace n
WHERE ${userSchemas}
ORDER BY n.nspname = 'shop' DESC, n.nspname`

const tablesSql = `
SELECT n.nspname AS schema, c.relname AS name, obj_description(c.oid, 'pg_class') AS comment,
       (CASE WHEN c.reltuples >= 0 THEN c.reltuples ELSE coalesce(s.n_live_tup, 0) END)::bigint AS rows,
       pg_total_relation_size(c.oid) AS bytes
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
LEFT JOIN pg_stat_user_tables s ON s.relid = c.oid
WHERE c.relkind IN ('r', 'p') AND ${userSchemas}
ORDER BY n.nspname, c.relname`

const columnsSql = `
SELECT n.nspname AS schema, c.relname AS table, a.attname AS name, format_type(a.atttypid, a.atttypmod) AS type,
       NOT a.attnotnull AS nullable, pg_get_expr(d.adbin, d.adrelid) AS default, col_description(c.oid, a.attnum) AS comment
FROM pg_attribute a
JOIN pg_class c ON c.oid = a.attrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
LEFT JOIN pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum
WHERE a.attnum > 0 AND NOT a.attisdropped AND c.relkind IN ('r', 'p') AND ${userSchemas}
ORDER BY n.nspname, c.relname, a.attnum`

const constraintsSql = `
SELECT n.nspname AS schema, c.relname AS table, con.conname AS name, con.contype AS kind, pg_get_constraintdef(con.oid) AS definition,
       ARRAY(SELECT a.attname FROM unnest(con.conkey) WITH ORDINALITY k (num, ord) JOIN pg_attribute a ON a.attrelid = con.conrelid AND a.attnum = k.num ORDER BY k.ord)::text[] AS columns,
       fn.nspname AS ref_schema, fc.relname AS ref_table,
       ARRAY(SELECT a.attname FROM unnest(con.confkey) WITH ORDINALITY k (num, ord) JOIN pg_attribute a ON a.attrelid = con.confrelid AND a.attnum = k.num ORDER BY k.ord)::text[] AS ref_columns
FROM pg_constraint con
JOIN pg_class c ON c.oid = con.conrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
LEFT JOIN pg_class fc ON fc.oid = con.confrelid
LEFT JOIN pg_namespace fn ON fn.oid = fc.relnamespace
WHERE ${userSchemas}
ORDER BY n.nspname, c.relname, con.conname`

const indexesSql = `
SELECT n.nspname AS schema, t.relname AS table, i.relname AS name, pg_get_indexdef(i.oid) AS definition,
       ix.indisunique AS unique, ix.indisprimary AS primary, pg_relation_size(i.oid) AS bytes,
       ARRAY(SELECT a.attname FROM unnest(ix.indkey) WITH ORDINALITY k (num, ord) JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = k.num ORDER BY k.ord)::text[] AS columns
FROM pg_index ix
JOIN pg_class i ON i.oid = ix.indexrelid
JOIN pg_class t ON t.oid = ix.indrelid
JOIN pg_namespace n ON n.oid = t.relnamespace
WHERE ${userSchemas}
ORDER BY n.nspname, t.relname, i.relname`

const key = row => `${row.schema}.${row.table}`

export async function readCatalog(pool) {
  const [schemas, tables, columns, constraints, indexes] = await Promise.all(
    [schemasSql, tablesSql, columnsSql, constraintsSql, indexesSql].map(sql => pool.query(sql).then(result => result.rows))
  )
  const byTable = new Map(tables.map(table => [`${table.schema}.${table.name}`, {
    name: table.name,
    comment: table.comment,
    rows: Number(table.rows),
    bytes: Number(table.bytes),
    columns: [],
    indexes: [],
    checks: [],
    uniques: [],
    foreignKeys: [],
    primaryKey: []
  }]))
  for (const column of columns) {
    byTable.get(key(column))?.columns.push({ name: column.name, type: column.type, nullable: column.nullable, default: column.default, comment: column.comment })
  }
  for (const index of indexes) {
    byTable.get(key(index))?.indexes.push({ name: index.name, definition: index.definition, unique: index.unique, primary: index.primary, bytes: Number(index.bytes), columns: index.columns })
  }
  for (const constraint of constraints) {
    const table = byTable.get(key(constraint))
    if (!table) continue
    if (constraint.kind === "p") table.primaryKey = constraint.columns
    if (constraint.kind === "u") table.uniques.push(constraint.columns)
    if (constraint.kind === "c" || constraint.kind === "x") table.checks.push({ name: constraint.name, definition: constraint.definition })
    if (constraint.kind === "f") table.foreignKeys.push({ name: constraint.name, columns: constraint.columns, schema: constraint.ref_schema, table: constraint.ref_table, refColumns: constraint.ref_columns })
  }
  return {
    schemas: schemas.map(schema => ({
      name: schema.name,
      comment: schema.comment,
      tables: tables.filter(table => table.schema === schema.name).map(table => byTable.get(`${table.schema}.${table.name}`))
    }))
  }
}

export async function relationFacts(client, names) {
  if (names.length === 0) return {}
  const { rows } = await client.query(`
    SELECT n.nspname || '.' || c.relname AS name,
           (CASE WHEN c.reltuples >= 0 THEN c.reltuples ELSE 0 END)::bigint AS rows,
           ARRAY(SELECT a.attname FROM pg_attribute a WHERE a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped)::text[] AS columns,
           ARRAY(SELECT a.attname FROM pg_index ix JOIN pg_attribute a ON a.attrelid = ix.indrelid AND a.attnum = ix.indkey[0] WHERE ix.indrelid = c.oid)::text[] AS leading_index_columns
    FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname || '.' || c.relname = ANY($1)`, [names])
  return Object.fromEntries(rows.map(row => [row.name, { rows: Number(row.rows), columns: row.columns, indexed: row.leading_index_columns }]))
}
