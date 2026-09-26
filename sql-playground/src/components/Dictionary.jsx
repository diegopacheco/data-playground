import { useMemo, useState } from "react"
import { compactCount, formatBytes, formatCount } from "../format.js"

function keyBadges(table, column) {
  const badges = []
  if (table.primaryKey.includes(column.name)) badges.push(["PK", "pk"])
  const foreign = table.foreignKeys.find(fk => fk.columns.includes(column.name))
  if (foreign) badges.push([`FK ${foreign.table}.${foreign.refColumns[foreign.columns.indexOf(column.name)]}`, "fk"])
  if (table.uniques.some(unique => unique.length === 1 && unique[0] === column.name) || table.indexes.some(index => index.unique && !index.primary && index.columns.length === 1 && index.columns[0] === column.name)) badges.push(["UQ", "uq"])
  if (table.indexes.some(index => !index.primary && index.columns[0] === column.name)) badges.push(["IDX", "idx"])
  return badges
}

export default function Dictionary({ catalog, schemaName, setSchemaName, tableName, setTableName, onPreview }) {
  const [filter, setFilter] = useState("")
  const schema = catalog.schemas.find(candidate => candidate.name === schemaName) ?? catalog.schemas[0]
  const tables = useMemo(() => {
    const needle = filter.trim().toLowerCase()
    if (!schema) return []
    if (!needle) return schema.tables
    return schema.tables.filter(table => table.name.includes(needle) || table.columns.some(column => column.name.includes(needle)) || (table.comment ?? "").toLowerCase().includes(needle))
  }, [schema, filter])
  if (!schema) return <div className="page-message">Loading catalog...</div>
  const table = schema.tables.find(candidate => candidate.name === tableName) ?? tables[0] ?? schema.tables[0]
  const referencedBy = catalog.schemas.flatMap(other => other.tables.flatMap(candidate => candidate.foreignKeys
    .filter(fk => fk.schema === schema.name && fk.table === table.name)
    .map(fk => ({ schema: other.name, table: candidate.name, columns: fk.columns, refColumns: fk.refColumns }))))
  const totalRows = schema.tables.reduce((sum, candidate) => sum + candidate.rows, 0)
  const totalBytes = schema.tables.reduce((sum, candidate) => sum + candidate.bytes, 0)
  return (
    <div className="dictionary">
      <div className="schema-chips">
        {catalog.schemas.map(candidate => (
          <button key={candidate.name} className={candidate.name === schema.name ? "active" : ""} onClick={() => { setSchemaName(candidate.name); setTableName(null) }}>
            {candidate.name}<small>{candidate.tables.length}</small>
          </button>
        ))}
      </div>
      <div className="dictionary-body">
        <aside className="table-list">
          <div className="schema-summary">
            <strong>{schema.name}</strong>
            <p>{schema.comment}</p>
            <span>{formatCount(totalRows)} rows · {formatBytes(totalBytes)}</span>
          </div>
          <input className="filter-input" placeholder="Filter tables or columns" value={filter} onChange={event => setFilter(event.target.value)} />
          {tables.map(candidate => (
            <button key={candidate.name} className={candidate.name === table.name ? "active" : ""} onClick={() => setTableName(candidate.name)}>
              <span>{candidate.name}</span>
              <small>{compactCount(candidate.rows)} · {formatBytes(candidate.bytes)}</small>
            </button>
          ))}
        </aside>
        <section className="table-detail">
          <header>
            <div>
              <p className="eyebrow">{schema.name}</p>
              <h1>{table.name}</h1>
              <p className="lede">{table.comment ?? "No description."}</p>
            </div>
            <div className="table-stats">
              <div><strong>{formatCount(table.rows)}</strong><small>rows (estimate)</small></div>
              <div><strong>{formatBytes(table.bytes)}</strong><small>with indexes</small></div>
              <div><strong>{table.columns.length}</strong><small>columns</small></div>
              <div><strong>{table.indexes.length}</strong><small>indexes</small></div>
              <button className="primary-button small" onClick={() => onPreview(`SELECT *\nFROM ${schema.name}.${table.name}\nLIMIT 100;`)}>Preview rows</button>
            </div>
          </header>
          <h2>Columns</h2>
          <table className="dict-table">
            <thead><tr><th>Column</th><th>Type</th><th>Null</th><th>Default</th><th>Keys</th><th>Description</th></tr></thead>
            <tbody>
              {table.columns.map(column => (
                <tr key={column.name}>
                  <td className="mono strong">{column.name}</td>
                  <td className="mono type">{column.type}</td>
                  <td>{column.nullable ? "yes" : <span className="not-null">not null</span>}</td>
                  <td className="mono muted">{column.default ?? ""}</td>
                  <td>{keyBadges(table, column).map(([text, kind]) => <span key={text} className={`key-badge ${kind}`}>{text}</span>)}</td>
                  <td>{column.comment ?? ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <h2>Indexes</h2>
          {table.indexes.length === 0 ? <p className="muted">No indexes.</p> : (
            <table className="dict-table">
              <thead><tr><th>Name</th><th>Definition</th><th>Size</th></tr></thead>
              <tbody>{table.indexes.map(index => <tr key={index.name}><td className="mono strong">{index.name}</td><td className="mono">{index.definition}</td><td>{formatBytes(index.bytes)}</td></tr>)}</tbody>
            </table>
          )}
          <div className="relations">
            <div>
              <h2>References</h2>
              {table.foreignKeys.length === 0 ? <p className="muted">None.</p> : table.foreignKeys.map(fk => (
                <button key={fk.name} className="relation-link" onClick={() => { setSchemaName(fk.schema); setTableName(fk.table) }}>
                  <span className="mono">{fk.columns.join(", ")}</span> → <span className="mono">{fk.schema}.{fk.table}({fk.refColumns.join(", ")})</span>
                </button>
              ))}
            </div>
            <div>
              <h2>Referenced by</h2>
              {referencedBy.length === 0 ? <p className="muted">None.</p> : referencedBy.map(ref => (
                <button key={`${ref.schema}.${ref.table}.${ref.columns}`} className="relation-link" onClick={() => { setSchemaName(ref.schema); setTableName(ref.table) }}>
                  <span className="mono">{ref.schema}.{ref.table}({ref.columns.join(", ")})</span> → <span className="mono">{ref.refColumns.join(", ")}</span>
                </button>
              ))}
            </div>
            <div>
              <h2>Checks</h2>
              {table.checks.length === 0 ? <p className="muted">None.</p> : table.checks.map(check => <p key={check.name} className="mono check">{check.definition}</p>)}
            </div>
          </div>
        </section>
      </div>
    </div>
  )
}
