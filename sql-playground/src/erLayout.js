export const box = { width: 250, header: 40, row: 22, gapX: 120, gapY: 34, margin: 30 }

export function tableHeight(table) {
  return box.header + table.columns.length * box.row + 8
}

export function layers(tables) {
  const names = new Set(tables.map(table => table.name))
  const depth = new Map(tables.map(table => [table.name, 0]))
  for (let pass = 0; pass < tables.length; pass++) {
    let changed = false
    for (const table of tables) {
      for (const fk of table.foreignKeys) {
        if (fk.table === table.name || !names.has(fk.table)) continue
        const wanted = depth.get(fk.table) + 1
        if (wanted > depth.get(table.name)) {
          depth.set(table.name, wanted)
          changed = true
        }
      }
    }
    if (!changed) break
  }
  return depth
}

export function layout(tables) {
  const depth = layers(tables)
  const columns = []
  for (const table of tables) {
    const index = depth.get(table.name)
    columns[index] = [...(columns[index] ?? []), table]
  }
  const positions = new Map()
  const ordered = columns.filter(Boolean)
  ordered.forEach((column, columnIndex) => {
    if (columnIndex > 0) {
      const center = table => {
        const targets = table.foreignKeys.map(fk => positions.get(fk.table)).filter(Boolean)
        return targets.length ? targets.reduce((sum, target) => sum + target.y, 0) / targets.length : Number.MAX_SAFE_INTEGER
      }
      column.sort((a, b) => center(a) - center(b) || a.name.localeCompare(b.name))
    } else {
      column.sort((a, b) => a.name.localeCompare(b.name))
    }
    let y = box.margin
    for (const table of column) {
      positions.set(table.name, { x: box.margin + columnIndex * (box.width + box.gapX), y, width: box.width, height: tableHeight(table) })
      y += tableHeight(table) + box.gapY
    }
  })
  const all = [...positions.values()]
  return {
    positions,
    width: Math.max(...all.map(p => p.x + p.width), 0) + box.margin + 40,
    height: Math.max(...all.map(p => p.y + p.height), 0) + box.margin
  }
}

export function columnY(position, table, columnName) {
  const index = Math.max(0, table.columns.findIndex(column => column.name === columnName))
  return position.y + box.header + index * box.row + box.row / 2 + 4
}

export function overlaps(a, b) {
  return a.x < b.x + b.width && b.x < a.x + a.width && a.y < b.y + b.height && b.y < a.y + a.height
}
