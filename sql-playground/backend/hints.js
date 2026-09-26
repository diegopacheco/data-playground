const bigTable = 100000

export function walk(node, visit, parent = null, depth = 0) {
  if (!node) return
  visit(node, parent, depth)
  for (const child of node.Plans ?? []) walk(child, visit, node, depth + 1)
}

export function planRelations(plan) {
  const names = new Set()
  walk(plan?.Plan, node => {
    if (node["Relation Name"]) names.add(`${node.Schema ?? "public"}.${node["Relation Name"]}`)
  })
  return [...names]
}

const operator = String.raw`(?:=|<>|!=|<=|>=|<|>|~~\*?|!~~\*?|IS\b|= ANY)`

export function filterColumns(filter, columns) {
  const plain = new Set()
  const expressions = []
  const known = new Set(columns ?? [])
  const direct = new RegExp(String.raw`\(?(?:\w+\.)?"?(\w+)"?\)?(?:::[\w ]+(?:\[\])?)?\s*${operator}`, "g")
  for (const match of filter.matchAll(direct)) if (known.has(match[1])) plain.add(match[1])
  const wrapped = new RegExp(String.raw`(\w+)\(\s*(?:\w+\.)?"?(\w+)"?\s*\)(?:::[\w ]+)?\s*${operator}`, "g")
  for (const match of filter.matchAll(wrapped)) {
    if (known.has(match[2])) {
      plain.delete(match[2])
      expressions.push({ fn: match[1], column: match[2] })
    }
  }
  const casts = new RegExp(String.raw`\(\s*(?:\w+\.)?"?(\w+)"?\s*\)::(date|text|integer|bigint)\s*${operator}`, "g")
  for (const match of filter.matchAll(casts)) {
    if (known.has(match[1])) {
      plain.delete(match[1])
      expressions.push({ fn: `cast to ${match[2]}`, column: match[1], cast: match[2] })
    }
  }
  return { plain: [...plain], expressions }
}

const fmt = value => Math.round(value).toLocaleString("en-US")

function seqScanHints(node, facts, analyzed, add) {
  if (node["Node Type"] !== "Seq Scan") return
  const name = `${node.Schema}.${node["Relation Name"]}`
  const fact = facts[name]
  if (!fact || fact.rows < bigTable) return
  const filter = node.Filter
  if (!filter) return
  const { plain, expressions } = filterColumns(filter, fact.columns)
  const kept = analyzed ? node["Actual Rows"] * (node["Actual Loops"] ?? 1) : node["Plan Rows"]
  const removed = analyzed ? node["Rows Removed by Filter"] ?? 0 : Math.max(fact.rows - kept, 0)
  const share = fact.rows > 0 ? kept / fact.rows : 1
  for (const expression of expressions) {
    const fix = expression.cast
      ? `CREATE INDEX ON ${name} ((${expression.column}::${expression.cast}));`
      : `CREATE INDEX ON ${name} (${expression.fn}(${expression.column}));`
    add("warning", `Function on ${expression.column} blocks index use`, `The filter wraps ${expression.column} in ${expression.fn}, so a plain index on ${expression.column} cannot be used and all ${fmt(fact.rows)} rows of ${name} are read. Compare the bare column against a range (for dates: col >= '2025-01-01' AND col < '2025-01-02') or create an expression index.`, fix)
  }
  if (plain.length === 0) return
  const indexed = plain.filter(column => fact.indexed.includes(column))
  if (share > 0.2) {
    add("info", `Filter keeps ${(share * 100).toFixed(0)}% of ${name}`, `The filter on ${plain.join(", ")} matches about ${fmt(kept)} of ${fmt(fact.rows)} rows. An index rarely helps when a large share of the table qualifies, a sequential scan reads pages in order and is cheaper. Narrow the predicate or aggregate ahead of time if this runs often.`)
    return
  }
  if (indexed.length === plain.length) {
    add("info", `Index on ${indexed.join(", ")} was not chosen`, `An index leads with ${indexed.join(", ")} but the planner preferred a sequential scan of ${name}. Statistics may be stale or the predicate uses a type or operator the index does not support. Run ANALYZE and check the column types on both sides of the comparison.`, `ANALYZE ${name};`)
    return
  }
  const missing = plain.filter(column => !fact.indexed.includes(column))
  add("critical", `Sequential scan on ${name} (${fmt(fact.rows)} rows)`, `Postgres reads every row of ${name} and throws away ${fmt(removed)} of them to keep ${fmt(kept)}. The filter is ${filter}. An index on ${missing.join(", ")} lets it jump straight to the matching rows.`, `CREATE INDEX ON ${name} (${missing.join(", ")});`)
}

function joinHints(node, facts, add) {
  if (node["Node Type"] !== "Nested Loop") return
  const inner = node.Plans?.[1]
  if (!inner) return
  let scanned = null
  walk(inner, child => {
    if (child["Node Type"] === "Seq Scan" && facts[`${child.Schema}.${child["Relation Name"]}`]?.rows >= bigTable) scanned = child
  })
  if (scanned) {
    const name = `${scanned.Schema}.${scanned["Relation Name"]}`
    add("critical", `Nested loop scans ${name} once per outer row`, `The inner side of a nested loop is a sequential scan of ${name} (${fmt(facts[name].rows)} rows). It repeats for every row coming from the outer side. Index the join column of ${name} so each lookup becomes an index probe.`)
  }
  if (!node["Join Filter"] && inner["Node Type"] === "Materialize" && node["Plan Rows"] > 1000000) {
    add("warning", "Possible cartesian product", `A nested loop without a join condition produces ${fmt(node["Plan Rows"])} rows. Check that every joined table has an ON condition.`)
  }
}

function memoryHints(node, add) {
  if (node["Sort Space Type"] === "Disk") {
    add("warning", `Sort spilled ${fmt(node["Sort Space Used"])} kB to disk`, `Sorting on ${(node["Sort Key"] ?? []).join(", ")} did not fit in work_mem and used an external merge on disk. Raise work_mem for this session or add an index that returns rows already ordered.`, "SET work_mem = '64MB';")
  }
  if ((node["Hash Batches"] ?? 1) > 1) {
    add("warning", `Hash split into ${node["Hash Batches"]} batches`, "The hash table of the join did not fit in work_mem and was written to disk in batches. Raise work_mem or filter the build side earlier.", "SET work_mem = '64MB';")
  }
  if ((node["Lossy Heap Blocks"] ?? 0) > 0) {
    add("info", "Lossy bitmap heap scan", `${fmt(node["Lossy Heap Blocks"])} heap blocks became lossy, so every row in them was rechecked. More work_mem keeps the bitmap exact.`, "SET work_mem = '64MB';")
  }
  if (node["Node Type"] === "Gather" || node["Node Type"] === "Gather Merge") {
    if (node["Workers Launched"] !== undefined && node["Workers Launched"] < node["Workers Planned"]) {
      add("info", "Fewer parallel workers than planned", `Planned ${node["Workers Planned"]} workers but launched ${node["Workers Launched"]}. The server ran out of max_parallel_workers.`)
    }
  }
}

function estimateHints(node, analyzed, add, seen, limited) {
  if (!analyzed || node["Actual Loops"] === 0 || limited.has(node)) return
  const actual = node["Actual Rows"]
  const planned = node["Plan Rows"]
  const ratio = Math.max(actual, 1) / Math.max(planned, 1)
  const target = node["Relation Name"] ? `${node.Schema}.${node["Relation Name"]}` : null
  if (Math.max(actual, planned) >= 1000 && (ratio > 10 || ratio < 0.1) && !seen.has(node["Node Type"] + target)) {
    seen.add(node["Node Type"] + target)
    add("warning", `Row estimate off by ${ratio > 1 ? fmt(ratio) : fmt(1 / ratio)}x in ${node["Node Type"]}`, `The planner expected ${fmt(planned)} rows and got ${fmt(actual)}. Bad estimates lead to the wrong join order or join method. Refresh statistics, or add extended statistics for correlated columns.`, target ? `ANALYZE ${target};` : undefined)
  }
  if (node["Node Type"] === "Index Only Scan" && (node["Heap Fetches"] ?? 0) > 1000) {
    add("info", `Index only scan visited the heap ${fmt(node["Heap Fetches"])} times`, "The visibility map is not up to date, so Postgres had to check the table anyway. VACUUM the table to make the scan truly index only.", target ? `VACUUM ${target};` : undefined)
  }
}

function topNHints(node, facts, add) {
  if (node["Node Type"] !== "Limit") return
  let sort = null
  walk(node.Plans?.[0], child => {
    if (!sort && (child["Node Type"] === "Sort" || child["Node Type"] === "Incremental Sort")) sort = child
  })
  if (!sort) return
  let big = null
  walk(sort, child => {
    if (child["Node Type"] === "Seq Scan" && facts[`${child.Schema}.${child["Relation Name"]}`]?.rows >= bigTable) big = child
  })
  if (!big) return
  const name = `${big.Schema}.${big["Relation Name"]}`
  const keys = (sort["Sort Key"] ?? []).map(key => key.replace(/^\(?\w+\./, "").replace(/\)$/, ""))
  add("warning", "Top N computed by sorting the whole table", `To return the first rows ordered by ${keys.join(", ")}, Postgres reads and sorts all of ${name}. An index on the sort key returns rows already ordered and stops after the limit.`, keys.every(key => /^[\w]+( DESC)?$/.test(key)) ? `CREATE INDEX ON ${name} (${keys.join(", ")});` : undefined)
}

function goodHints(node, add, seen) {
  const type = node["Node Type"]
  if ((type === "Index Scan" || type === "Index Only Scan" || type === "Bitmap Index Scan") && !seen.has(node["Index Name"])) {
    seen.add(node["Index Name"])
    add("good", `${type} on ${node["Index Name"]}`, `Rows are located through the index${node["Index Cond"] ? ` with ${node["Index Cond"]}` : ""}.`)
  }
}

function sqlHints(sql, facts, rowCount, add) {
  const text = sql.replace(/'(?:[^']|'')*'/g, match => (match.startsWith("'%") ? "'%'" : "''"))
  if (/select\s+(\w+\.)?\*/i.test(text)) {
    add("info", "SELECT * reads every column", "Selecting only the columns you need reduces I/O, network transfer and allows index only scans.")
  }
  const offset = sql.match(/\boffset\s+(\d+)/i)
  if (offset && Number(offset[1]) >= 1000) {
    add("warning", `OFFSET ${fmt(Number(offset[1]))} discards rows`, "Postgres computes and throws away every skipped row, so deep pages get slower and slower. Use keyset pagination: WHERE id > last_seen_id ORDER BY id LIMIT n.")
  }
  if (/\bnot\s+in\s*\(\s*select/i.test(text)) {
    add("warning", "NOT IN with a subquery", "NOT IN returns no rows when the subquery yields a NULL and often cannot use an anti join. NOT EXISTS has the semantics you expect and plans as a hash anti join.")
  }
  const like = sql.match(/(?:(\w+)\.)?(\w+)\s+i?like\s+'%/i)
  if (like) {
    const table = Object.entries(facts).find(([, fact]) => fact.columns.includes(like[2]))
    add("warning", `Leading wildcard on ${like[2]}`, "A pattern that starts with % cannot use a btree index. A trigram GIN index supports LIKE and ILIKE with wildcards anywhere.", table ? `CREATE INDEX ON ${table[0]} USING gin (${like[2]} gin_trgm_ops);` : undefined)
  }
  if (/\bcount\s*\(\s*\*\s*\)/i.test(text) && !/\bwhere\b|\bgroup\s+by\b|\bjoin\b/i.test(text)) {
    const table = Object.entries(facts).find(([, fact]) => fact.rows >= bigTable)
    if (table) add("info", `Exact count of ${table[0]}`, "An exact count has to visit every visible row. When an approximate number is enough, read the planner estimate instead.", `SELECT reltuples::bigint FROM pg_class WHERE oid = '${table[0]}'::regclass;`)
  }
  if (!/\blimit\b|\bfetch\s+first\b/i.test(text) && rowCount > 10000) {
    add("info", `${fmt(rowCount)} rows returned`, "Large result sets cost memory and network on both sides. Paginate with LIMIT, or aggregate in the database.")
  }
}

const order = { critical: 0, warning: 1, info: 2, good: 3 }

export function hintsFor({ sql, plan, analyzed, facts = {}, rowCount = 0 }) {
  const hints = []
  const titles = new Set()
  const add = (level, title, detail, fix) => {
    if (titles.has(title)) return
    titles.add(title)
    hints.push({ level, title, detail, ...(fix ? { fix } : {}) })
  }
  const seen = new Set()
  const good = new Set()
  const limited = new Set()
  walk(plan?.Plan, node => {
    if (node["Node Type"] === "Limit") walk(node, child => limited.add(child))
  })
  walk(plan?.Plan, node => {
    seqScanHints(node, facts, analyzed, add)
    joinHints(node, facts, add)
    memoryHints(node, add)
    estimateHints(node, analyzed, add, seen, limited)
    topNHints(node, facts, add)
    goodHints(node, add, good)
  })
  sqlHints(sql, facts, rowCount, add)
  if (plan?.JIT && analyzed) {
    const jit = plan.JIT.Timing?.Total ?? 0
    const total = plan["Execution Time"] ?? 0
    if (total > 0 && jit / total > 0.2) {
      add("info", `JIT took ${(jit / total * 100).toFixed(0)}% of the run`, "Just in time compilation costs more than it saves for this query. Disable it for short analytic queries.", "SET jit = off;")
    }
  }
  if (plan && !hints.some(hint => hint.level === "critical" || hint.level === "warning")) {
    add("good", "No obvious problems", "The plan has no sequential scans on big filtered tables, no spills and no bad estimates.")
  }
  return hints.sort((a, b) => order[a.level] - order[b.level])
}
