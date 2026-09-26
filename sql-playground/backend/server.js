import { createServer } from "node:http"
import { readCatalog } from "./catalog.js"
import { createPool } from "./db.js"
import { loadProblems, resetProblem, runRace } from "./problems.js"
import { readPorts } from "./ports.js"
import { cancelRunning, runQuery } from "./query.js"
import { ensureSeeded, status } from "./seed.js"

const ports = readPorts()
const pool = createPool()
const problems = loadProblems()

function send(response, code, body) {
  response.writeHead(code, { "content-type": "application/json" })
  response.end(JSON.stringify(body))
}

async function body(request) {
  const chunks = []
  for await (const chunk of request) chunks.push(chunk)
  return chunks.length ? JSON.parse(Buffer.concat(chunks).toString("utf8")) : {}
}

const routes = [
  ["GET", /^\/api\/status$/, async () => ({ ...status, problems: problems.length })],
  ["GET", /^\/api\/catalog$/, async () => readCatalog(pool)],
  ["GET", /^\/api\/problems$/, async () => problems],
  ["POST", /^\/api\/query$/, async request => {
    const { sql, analyze } = await body(request)
    return runQuery(pool, String(sql ?? ""), { analyze: Boolean(analyze) })
  }],
  ["POST", /^\/api\/cancel$/, async () => ({ cancelled: await cancelRunning(pool) })],
  ["POST", /^\/api\/problems\/([\w-]+)\/reset$/, async (request, id) => {
    await resetProblem(pool, find(id))
    return { reset: id }
  }],
  ["POST", /^\/api\/problems\/([\w-]+)\/race$/, async (request, id) => {
    const { mode } = await body(request)
    if (mode !== "naive" && mode !== "safe") throw Object.assign(new Error("mode must be naive or safe"), { status: 400 })
    return runRace(pool, find(id), mode)
  }]
]

function find(id) {
  const problem = problems.find(candidate => candidate.id === id)
  if (!problem) throw Object.assign(new Error(`unknown problem ${id}`), { status: 404 })
  return problem
}

const server = createServer(async (request, response) => {
  const path = new URL(request.url, "http://localhost").pathname
  for (const [method, pattern, handler] of routes) {
    const match = path.match(pattern)
    if (!match || request.method !== method) continue
    if (status.phase !== "ready" && !path.endsWith("/status")) return send(response, 503, { error: status.label })
    try {
      return send(response, 200, await handler(request, ...match.slice(1)))
    } catch (error) {
      return send(response, error.status ?? 500, { error: error.message })
    }
  }
  send(response, 404, { error: "not found" })
})

server.listen(ports.backend, "127.0.0.1", () => {
  console.log(`backend listening on http://localhost:${ports.backend}`)
  ensureSeeded(pool, problems).then(() => console.log(`database ${status.phase}${status.error ? `: ${status.error}` : ""}`))
})

for (const signal of ["SIGINT", "SIGTERM"]) {
  process.on(signal, () => {
    server.close()
    pool.end().finally(() => process.exit(0))
  })
}
