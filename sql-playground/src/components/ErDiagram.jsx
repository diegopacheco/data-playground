import { useMemo, useState } from "react"
import { compactCount } from "../format.js"
import { box, columnY, layout } from "../erLayout.js"

function edgePath(from, to, fromY, toY) {
  if (from === to) {
    const x = from.x + from.width
    return `M ${x} ${fromY} C ${x + 60} ${fromY}, ${x + 60} ${toY}, ${x} ${toY}`
  }
  const leftToRight = from.x > to.x
  const startX = leftToRight ? from.x : from.x + from.width
  const endX = leftToRight ? to.x + to.width : to.x
  const bend = Math.max(50, Math.abs(startX - endX) / 2)
  const direction = leftToRight ? -1 : 1
  if (from.x === to.x) {
    const x = from.x
    return `M ${x} ${fromY} C ${x - 70} ${fromY}, ${x - 70} ${toY}, ${x} ${toY}`
  }
  return `M ${startX} ${fromY} C ${startX + direction * bend} ${fromY}, ${endX - direction * bend} ${toY}, ${endX} ${toY}`
}

export default function ErDiagram({ catalog, schemaName, setSchemaName, onOpenTable }) {
  const [focus, setFocus] = useState(null)
  const [zoom, setZoom] = useState(1)
  const schema = catalog.schemas.find(candidate => candidate.name === schemaName) ?? catalog.schemas[0]
  const tables = schema?.tables ?? []
  const graph = useMemo(() => layout(tables), [tables])
  if (!schema) return <div className="page-message">Loading catalog...</div>
  const byName = new Map(tables.map(table => [table.name, table]))
  const edges = tables.flatMap(table => table.foreignKeys
    .filter(fk => byName.has(fk.table) && fk.schema === schema.name)
    .map(fk => ({ from: table, to: byName.get(fk.table), fk })))
  const related = name => !focus || name === focus || edges.some(edge => (edge.from.name === focus && edge.to.name === name) || (edge.to.name === focus && edge.from.name === name))
  return (
    <div className="er">
      <div className="schema-chips">
        {catalog.schemas.map(candidate => (
          <button key={candidate.name} className={candidate.name === schema.name ? "active" : ""} onClick={() => setSchemaName(candidate.name)}>
            {candidate.name}<small>{candidate.tables.length}</small>
          </button>
        ))}
        <div className="toolbar-spacer" />
        <div className="zoom-controls">
          <button className="ghost-button" onClick={() => setZoom(Math.max(0.4, zoom - 0.1))}>-</button>
          <span>{Math.round(zoom * 100)}%</span>
          <button className="ghost-button" onClick={() => setZoom(Math.min(1.6, zoom + 0.1))}>+</button>
          <button className="ghost-button" onClick={() => setZoom(1)}>Reset</button>
        </div>
      </div>
      <p className="er-help">Hover a table to highlight its relationships. Click a table to open it in the Dictionary. Arrows go from the foreign key column to the referenced column.</p>
      <div className="er-canvas">
        <svg width={graph.width * zoom} height={graph.height * zoom} viewBox={`0 0 ${graph.width} ${graph.height}`}>
          <defs>
            <marker id="er-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
              <path d="M 0 0 L 10 5 L 0 10 z" className="er-arrow" />
            </marker>
          </defs>
          {edges.map(({ from, to, fk }) => {
            const fromPosition = graph.positions.get(from.name)
            const toPosition = graph.positions.get(to.name)
            const active = !focus || focus === from.name || focus === to.name
            return (
              <path
                key={`${from.name}-${fk.name}`}
                d={edgePath(fromPosition, toPosition, columnY(fromPosition, from, fk.columns[0]), columnY(toPosition, to, fk.refColumns[0]))}
                className={`er-edge ${active ? "" : "dim"} ${focus && active ? "hot" : ""}`}
                markerEnd="url(#er-arrow)"
              />
            )
          })}
          {tables.map(table => {
            const position = graph.positions.get(table.name)
            const foreign = new Set(table.foreignKeys.flatMap(fk => fk.columns))
            return (
              <g
                key={table.name}
                className={`er-table ${related(table.name) ? "" : "dim"} ${focus === table.name ? "focus" : ""}`}
                transform={`translate(${position.x} ${position.y})`}
                onMouseEnter={() => setFocus(table.name)}
                onMouseLeave={() => setFocus(null)}
                onClick={() => onOpenTable(schema.name, table.name)}
              >
                <rect width={position.width} height={position.height} rx="10" className="er-box" />
                <path d={`M 0 10 a 10 10 0 0 1 10 -10 h ${position.width - 20} a 10 10 0 0 1 10 10 v ${box.header - 10} h ${-position.width} z`} className="er-head" />
                <text x="14" y="25" className="er-title">{table.name}</text>
                <text x={position.width - 14} y="25" className="er-rows" textAnchor="end">{compactCount(table.rows)} rows</text>
                {table.columns.map((column, index) => {
                  const y = box.header + index * box.row + box.row / 2 + 8
                  const primary = table.primaryKey.includes(column.name)
                  return (
                    <g key={column.name}>
                      {primary && <text x="12" y={y} className="er-key pk">PK</text>}
                      {!primary && foreign.has(column.name) && <text x="12" y={y} className="er-key fk">FK</text>}
                      <text x="38" y={y} className={`er-column ${primary ? "primary" : ""}`}>{column.name}</text>
                      <text x={position.width - 12} y={y} className="er-type" textAnchor="end">{column.type.replace("timestamp with time zone", "timestamptz").replace("character varying", "varchar").slice(0, 16)}</text>
                    </g>
                  )
                })}
              </g>
            )
          })}
        </svg>
      </div>
    </div>
  )
}
