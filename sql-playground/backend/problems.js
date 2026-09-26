import { existsSync, readdirSync, readFileSync } from "node:fs"
import { join } from "node:path"
import { connectClient, rawText } from "./db.js"
import { root } from "./ports.js"

export const joinTypes = ["inner", "left", "right", "full", "cross", "self", "semi", "anti", "lateral"]
const problemsDir = join(root, "problems")

function read(dir, name) {
  const file = join(dir, name)
  return existsSync(file) ? readFileSync(file, "utf8").trim() : ""
}

export function loadProblems() {
  return readdirSync(problemsDir)
    .filter(name => existsSync(join(problemsDir, name, "problem.json")))
    .sort()
    .map(id => {
      const dir = join(problemsDir, id)
      const meta = JSON.parse(read(dir, "problem.json"))
      return {
        id,
        ...meta,
        setup: read(dir, "setup.sql"),
        race: {
          ...meta.race,
          prepare: read(dir, "prepare.sql"),
          naive: read(dir, "naive.sql"),
          safe: read(dir, "safe.sql"),
          safePrepare: read(dir, "safe-prepare.sql"),
          check: read(dir, "check.sql")
        },
        joins: joinTypes.map(type => ({ type, ...meta.joins[type], sql: read(join(dir, "joins"), `${type}.sql`) }))
      }
    })
}

export async function resetProblem(pool, problem) {
  await pool.query(problem.setup)
}

async function runClient(client, sql, iterations, errors) {
  for (let i = 0; i < iterations; i++) {
    try {
      await client.query(sql)
    } catch (error) {
      const key = `${error.code ?? "error"} ${error.message}`
      errors.set(key, (errors.get(key) ?? 0) + 1)
    }
  }
}

export async function runRace(pool, problem, mode) {
  const race = problem.race
  await pool.query(problem.setup)
  await pool.query(race.prepare)
  if (mode === "safe" && race.safePrepare) await pool.query(race.safePrepare)
  const clients = await Promise.all(Array.from({ length: race.clients }, () => connectClient()))
  await Promise.all(clients.map(client => client.query("SET deadlock_timeout = '50ms'")))
  const errors = new Map()
  const started = performance.now()
  try {
    await Promise.all(clients.map(client => runClient(client, race[mode], race.iterations, errors)))
  } finally {
    await Promise.all(clients.map(client => client.end().catch(() => {})))
  }
  const elapsedMs = performance.now() - started
  const check = await pool.query({ text: race.check, rowMode: "array", types: rawText })
  const okIndex = check.fields.findIndex(field => field.name === "ok")
  return {
    mode,
    clients: race.clients,
    iterations: race.iterations,
    elapsedMs,
    ok: check.rows.length > 0 && check.rows.every(row => row[okIndex] === "t"),
    errors: [...errors].map(([message, count]) => ({ message, count })),
    check: { fields: check.fields.map(field => field.name), rows: check.rows }
  }
}
