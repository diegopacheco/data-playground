import { readdirSync, readFileSync } from "node:fs"
import { join } from "node:path"
import { root } from "./ports.js"

export const seedVersion = "1"
const seedDir = join(root, "backend", "seed")

export const status = { phase: "connecting", step: 0, total: 0, label: "Waiting for PostgreSQL", error: null }

function set(values) {
  Object.assign(status, values)
}

async function waitForDatabase(pool) {
  for (let attempt = 0; attempt < 120; attempt++) {
    try {
      await pool.query("SELECT 1")
      return
    } catch {
      await new Promise(resolve => setTimeout(resolve, 1000))
    }
  }
  throw new Error("PostgreSQL did not accept connections")
}

async function seeded(pool) {
  const { rows } = await pool.query("SELECT to_regclass('playground.meta') IS NOT NULL AS present")
  if (!rows[0].present) return false
  const marker = await pool.query("SELECT value FROM playground.meta WHERE key = 'seed_version'")
  return marker.rows[0]?.value === seedVersion
}

function steps(problems) {
  const files = readdirSync(seedDir).filter(name => name.endsWith(".sql")).sort()
  return [
    ...files.map(name => ({ label: name.replace(/^\d+-/, "").replace(/\.sql$/, "").replaceAll("-", " "), sql: readFileSync(join(seedDir, name), "utf8") })),
    ...problems.map(problem => ({ label: `problem ${problem.schema}`, sql: problem.setup }))
  ]
}

export async function ensureSeeded(pool, problems) {
  try {
    await waitForDatabase(pool)
    if (await seeded(pool)) {
      set({ phase: "ready", label: "Database ready" })
      return
    }
    const plan = steps(problems)
    set({ phase: "seeding", total: plan.length })
    for (const [index, step] of plan.entries()) {
      set({ step: index + 1, label: `Seeding ${step.label}` })
      await pool.query(step.sql)
    }
    await pool.query("CREATE SCHEMA IF NOT EXISTS playground; CREATE TABLE IF NOT EXISTS playground.meta (key text PRIMARY KEY, value text NOT NULL)")
    await pool.query("INSERT INTO playground.meta VALUES ('seed_version', $1) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value", [seedVersion])
    set({ phase: "ready", label: "Database ready" })
  } catch (error) {
    set({ phase: "error", label: "Seeding failed", error: error.message })
  }
}
