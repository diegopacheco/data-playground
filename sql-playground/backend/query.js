import { relationFacts } from "./catalog.js"
import { hintsFor, planRelations } from "./hints.js"
import { rawText } from "./db.js"

export const rowLimit = 1000
const running = new Set()
const cursorPrefix = "DECLARE playground_cursor NO SCROLL CURSOR FOR "

export function stripComments(sql) {
  return sql.replace(/\/\*[\s\S]*?\*\//g, " ").replace(/--[^\n]*/g, " ")
}

export function normalize(sql) {
  return sql.trim().replace(/;+\s*$/, "").trim()
}

export function isSingleStatement(sql) {
  return !stripComments(sql).replace(/'(?:[^']|'')*'/g, "''").replace(/\$\$[\s\S]*?\$\$/g, "").includes(";")
}

export function firstKeyword(sql) {
  return (stripComments(sql).trim().match(/^[a-z]+/i)?.[0] ?? "").toLowerCase()
}

const readKeywords = new Set(["select", "with", "values", "table"])
const explainKeywords = new Set(["select", "with", "values", "table", "insert", "update", "delete", "merge"])

function shape(result) {
  return {
    command: result.command,
    rowCount: result.rowCount ?? result.rows?.length ?? 0,
    fields: (result.fields ?? []).map(field => ({ name: field.name, typeId: field.dataTypeID })),
    rows: (result.rows ?? []).slice(0, rowLimit),
    truncated: (result.rows?.length ?? 0) > rowLimit
  }
}

async function runCursor(client, text) {
  await client.query("BEGIN")
  try {
    await client.query("SET LOCAL cursor_tuple_fraction = 1")
    await client.query(`${cursorPrefix}${text}`)
    const page = await client.query({ text: `FETCH ${rowLimit} FROM playground_cursor`, rowMode: "array", types: rawText })
    const rest = await client.query("MOVE FORWARD ALL IN playground_cursor")
    await client.query("COMMIT")
    const total = page.rows.length + (rest.rowCount ?? 0)
    return [{ ...shape(page), command: "SELECT", rowCount: total, truncated: total > page.rows.length }]
  } catch (error) {
    await client.query("ROLLBACK").catch(() => {})
    if (error.position) error.position = String(Math.max(1, Number(error.position) - cursorPrefix.length))
    throw error
  }
}

async function runPlain(client, text) {
  const result = await client.query({ text, rowMode: "array", types: rawText })
  return (Array.isArray(result) ? result : [result]).map(shape)
}

async function explain(client, text, analyze) {
  const options = analyze ? "ANALYZE, BUFFERS, VERBOSE, SETTINGS, FORMAT JSON" : "VERBOSE, SETTINGS, FORMAT JSON"
  if (!analyze) {
    const { rows } = await client.query(`EXPLAIN (${options}) ${text}`)
    return rows[0]["QUERY PLAN"][0]
  }
  await client.query("BEGIN")
  try {
    const { rows } = await client.query(`EXPLAIN (${options}) ${text}`)
    return rows[0]["QUERY PLAN"][0]
  } finally {
    await client.query("ROLLBACK").catch(() => {})
  }
}

export async function runQuery(pool, sql, { analyze = false } = {}) {
  const text = normalize(sql)
  if (!text) return { error: { message: "Nothing to run" } }
  const offset = sql.length - sql.trimStart().length
  const client = await pool.connect()
  const notices = []
  const onNotice = notice => notices.push(`${notice.severity}: ${notice.message}`)
  client.on("notice", onNotice)
  running.add(client.processID)
  const single = isSingleStatement(text)
  const keyword = firstKeyword(text)
  try {
    let results
    const started = performance.now()
    try {
      results = single && readKeywords.has(keyword) ? await runCursor(client, text) : await runPlain(client, text)
    } catch (error) {
      if (error.code !== "0A000" && error.code !== "42601") throw error
      results = await runPlain(client, text)
    }
    const elapsedMs = performance.now() - started
    let plan = null
    let planError = null
    if (single && explainKeywords.has(keyword)) {
      try {
        plan = await explain(client, text, analyze)
      } catch (error) {
        planError = error.message
      }
    }
    const facts = plan ? await relationFacts(client, planRelations(plan)) : {}
    const last = results[results.length - 1]
    return {
      elapsedMs,
      results,
      notices,
      plan,
      planError,
      analyzed: Boolean(plan && analyze),
      hints: hintsFor({ sql: text, plan, analyzed: analyze, facts, rowCount: last?.rowCount ?? 0 })
    }
  } catch (error) {
    return {
      notices,
      error: { message: error.message, code: error.code, position: error.position ? Number(error.position) + offset : null, detail: error.detail, hint: error.hint }
    }
  } finally {
    running.delete(client.processID)
    client.off("notice", onNotice)
    client.release()
  }
}

export async function cancelRunning(pool) {
  const pids = [...running]
  for (const pid of pids) await pool.query("SELECT pg_cancel_backend($1)", [pid])
  return pids.length
}
