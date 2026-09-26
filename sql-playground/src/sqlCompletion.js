const keywords = [
  "SELECT", "FROM", "WHERE", "AND", "OR", "NOT", "IN", "EXISTS", "BETWEEN", "LIKE", "ILIKE", "IS NULL", "IS NOT NULL",
  "JOIN", "INNER JOIN", "LEFT JOIN", "RIGHT JOIN", "FULL OUTER JOIN", "CROSS JOIN", "LEFT JOIN LATERAL", "CROSS JOIN LATERAL", "ON", "USING",
  "GROUP BY", "HAVING", "ORDER BY", "ASC", "DESC", "NULLS FIRST", "NULLS LAST", "LIMIT", "OFFSET", "FETCH FIRST",
  "DISTINCT", "DISTINCT ON", "AS", "CASE", "WHEN", "THEN", "ELSE", "END", "UNION", "UNION ALL", "INTERSECT", "EXCEPT",
  "WITH", "WITH RECURSIVE", "INSERT INTO", "VALUES", "UPDATE", "SET", "DELETE FROM", "RETURNING", "ON CONFLICT", "DO NOTHING", "DO UPDATE SET",
  "MERGE INTO", "CREATE TABLE", "CREATE INDEX", "CREATE UNIQUE INDEX", "CONCURRENTLY", "DROP INDEX", "ALTER TABLE", "ADD CONSTRAINT",
  "PRIMARY KEY", "FOREIGN KEY", "REFERENCES", "CHECK", "UNIQUE", "DEFAULT", "EXCLUDE USING gist",
  "BEGIN", "COMMIT", "ROLLBACK", "FOR UPDATE", "FOR UPDATE SKIP LOCKED", "FOR SHARE", "NOWAIT",
  "EXPLAIN", "EXPLAIN ANALYZE", "ANALYZE", "VACUUM", "WINDOW", "OVER", "PARTITION BY", "ROWS BETWEEN", "FILTER",
  "MATERIALIZED", "NOT MATERIALIZED", "TRUE", "FALSE", "NULL", "INTERVAL", "CURRENT_DATE", "NOW()"
]

const functions = [
  "count", "sum", "avg", "min", "max", "coalesce", "nullif", "greatest", "least", "round", "floor", "ceil", "abs",
  "lower", "upper", "length", "substring", "trim", "concat", "string_agg", "array_agg", "jsonb_agg", "json_build_object",
  "date_trunc", "extract", "age", "now", "to_char", "generate_series", "row_number", "rank", "dense_rank", "lag", "lead",
  "first_value", "percentile_cont", "random", "daterange", "tstzrange", "lower_inf", "pg_sleep", "pg_advisory_xact_lock",
  "pg_size_pretty", "pg_total_relation_size", "pg_relation_size", "pg_backend_pid"
]

let catalog = { schemas: [] }

export function setCompletionCatalog(next) {
  catalog = next ?? { schemas: [] }
}

function allTables() {
  return catalog.schemas.flatMap(schema => schema.tables.map(table => ({ schema: schema.name, ...table })))
}

export function aliasesIn(text) {
  const aliases = new Map()
  const tables = allTables()
  const pattern = /\b(?:from|join)\s+(?:(\w+)\.)?(\w+)(?:\s+(?:as\s+)?(\w+))?/gi
  for (const match of text.matchAll(pattern)) {
    const [, schema, name, alias] = match
    const table = tables.find(candidate => candidate.name === name && (!schema || candidate.schema === schema))
    if (!table) continue
    aliases.set(name.toLowerCase(), table)
    const reserved = /^(on|where|join|inner|left|right|full|cross|group|order|limit|using|natural|lateral|and|or)$/i
    if (alias && !reserved.test(alias)) aliases.set(alias.toLowerCase(), table)
  }
  return aliases
}

function columnItems(monaco, table, range, sortPrefix) {
  return table.columns.map(column => ({
    label: column.name,
    kind: monaco.languages.CompletionItemKind.Field,
    detail: `${column.type} · ${table.schema}.${table.name}`,
    documentation: column.comment ?? undefined,
    insertText: column.name,
    sortText: `${sortPrefix}${column.name}`,
    range
  }))
}

export function registerCompletion(monaco) {
  monaco.languages.registerCompletionItemProvider("pgsql", {
    triggerCharacters: ["."],
    provideCompletionItems(model, position) {
      const word = model.getWordUntilPosition(position)
      const range = { startLineNumber: position.lineNumber, endLineNumber: position.lineNumber, startColumn: word.startColumn, endColumn: word.endColumn }
      const before = model.getLineContent(position.lineNumber).slice(0, word.startColumn - 1)
      const qualifier = before.match(/(\w+)\.$/)?.[1]
      const text = model.getValue()
      const aliases = aliasesIn(text)
      if (qualifier) {
        const schema = catalog.schemas.find(candidate => candidate.name === qualifier)
        if (schema) {
          return {
            suggestions: schema.tables.map(table => ({
              label: table.name,
              kind: monaco.languages.CompletionItemKind.Struct,
              detail: `${table.rows.toLocaleString("en-US")} rows`,
              documentation: table.comment ?? undefined,
              insertText: table.name,
              range
            }))
          }
        }
        const table = aliases.get(qualifier.toLowerCase())
        return { suggestions: table ? columnItems(monaco, table, range, "0") : [] }
      }
      const inQuery = [...new Set(aliases.values())].flatMap(table => columnItems(monaco, table, range, "1"))
      const tables = allTables().map(table => ({
        label: `${table.schema}.${table.name}`,
        kind: monaco.languages.CompletionItemKind.Struct,
        detail: `${table.rows.toLocaleString("en-US")} rows`,
        documentation: table.comment ?? undefined,
        insertText: `${table.schema}.${table.name}`,
        filterText: `${table.name} ${table.schema}.${table.name}`,
        sortText: `2${table.name}`,
        range
      }))
      const schemas = catalog.schemas.map(schema => ({
        label: schema.name,
        kind: monaco.languages.CompletionItemKind.Module,
        detail: "schema",
        insertText: schema.name,
        sortText: `3${schema.name}`,
        range
      }))
      const words = keywords.map(keyword => ({
        label: keyword,
        kind: monaco.languages.CompletionItemKind.Keyword,
        insertText: keyword,
        sortText: `4${keyword}`,
        range
      }))
      const calls = functions.map(name => ({
        label: `${name}()`,
        kind: monaco.languages.CompletionItemKind.Function,
        insertText: `${name}($0)`,
        insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet,
        sortText: `5${name}`,
        range
      }))
      return { suggestions: [...inQuery, ...tables, ...schemas, ...words, ...calls] }
    }
  })
}
