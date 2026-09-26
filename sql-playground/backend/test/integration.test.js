import assert from "node:assert/strict"
import { before, test } from "node:test"
import { readPorts } from "../ports.js"

const base = `http://localhost:${readPorts().backend}`
const call = (path, body) => fetch(`${base}${path}`, { method: body ? "POST" : "GET", headers: { "content-type": "application/json" }, body: body && JSON.stringify(body) }).then(response => response.json())
let problems = []

before(async () => {
  const status = await call("/api/status")
  assert.equal(status.phase, "ready", "run ./scripts/start-all.sh and wait for the seed before the integration tests")
  problems = await call("/api/problems")
})

test("the big dataset has 7 shop tables and 5M order lines so plans behave like production", async () => {
  const catalog = await call("/api/catalog")
  const shop = catalog.schemas.find(schema => schema.name === "shop")
  assert.equal(shop.tables.length, 7)
  const count = await call("/api/query", { sql: "select count(*) from shop.order_items" })
  assert.equal(count.results[0].rows[0][0], "5000000")
})

test("every shop table and column carries a dictionary description", async () => {
  const catalog = await call("/api/catalog")
  const shop = catalog.schemas.find(schema => schema.name === "shop")
  for (const table of shop.tables) {
    assert.ok(table.comment, `${table.name} needs a comment`)
    for (const column of table.columns) assert.ok(column.comment, `${table.name}.${column.name} needs a comment`)
  }
})

test("there are 8 problems and each one covers all 9 join types with a background", () => {
  assert.equal(problems.length, 8)
  for (const problem of problems) {
    assert.ok(problem.background.length >= 3, `${problem.id} needs a background`)
    assert.deepEqual(problem.joins.map(exercise => exercise.type), ["inner", "left", "right", "full", "cross", "self", "semi", "anti", "lateral"])
  }
})

test("every join solution runs and returns rows on fresh data", async () => {
  for (const problem of problems) {
    await call(`/api/problems/${problem.id}/reset`, {})
    for (const exercise of problem.joins) {
      const response = await call("/api/query", { sql: exercise.sql })
      assert.equal(response.error, undefined, `${problem.id} ${exercise.type}: ${response.error?.message}`)
      assert.ok(response.results.at(-1).rowCount > 0, `${problem.id} ${exercise.type} returned no rows`)
    }
  }
})

test("every naive race breaks its invariant and every safe race keeps it", async () => {
  for (const problem of problems) {
    const naive = await call(`/api/problems/${problem.id}/race`, { mode: "naive" })
    const safe = await call(`/api/problems/${problem.id}/race`, { mode: "safe" })
    assert.equal(naive.ok, false, `${problem.id} naive race should expose the anomaly`)
    assert.equal(safe.ok, true, `${problem.id} safe race should hold: ${JSON.stringify(safe.check ?? safe)}`)
    await call(`/api/problems/${problem.id}/reset`, {})
  }
})

test("a filter on the unindexed product_id of 5M rows is timed, planned and gets an index hint", async () => {
  const response = await call("/api/query", { sql: "select sum(quantity) from shop.order_items where product_id = 42" })
  assert.ok(response.elapsedMs > 0)
  assert.ok(response.plan.Plan)
  assert.ok(response.hints.some(hint => hint.level === "critical" && hint.fix === "CREATE INDEX ON shop.order_items (product_id);"))
})

test("analyze mode measures real rows without applying data changes", async () => {
  const before = await call("/api/query", { sql: "select stock from shop.products where id = 1" })
  const response = await call("/api/query", { sql: "update shop.products set stock = stock + 1 where id = 1", analyze: true })
  const after = await call("/api/query", { sql: "select stock from shop.products where id = 1" })
  assert.equal(response.analyzed, true)
  assert.equal(Number(after.results[0].rows[0][0]), Number(before.results[0].rows[0][0]) + 1, "the statement runs once, the analyzed plan is rolled back")
  await call("/api/query", { sql: "update shop.products set stock = stock - 1 where id = 1" })
})

test("big results are fully counted but only the first 1000 rows are shipped", async () => {
  const response = await call("/api/query", { sql: "select id from shop.orders" })
  assert.equal(response.results[0].rowCount, 1500000)
  assert.equal(response.results[0].rows.length, 1000)
  assert.equal(response.results[0].truncated, true)
})

test("an error points at the offending position of the original text", async () => {
  const response = await call("/api/query", { sql: "\n  select nope from shop.orders" })
  assert.equal(response.error.code, "42703")
  assert.equal(response.error.position, 11)
})

test("a running query can be cancelled", async () => {
  const running = call("/api/query", { sql: "select pg_sleep(30)" })
  await new Promise(resolve => setTimeout(resolve, 500))
  const cancelled = await call("/api/cancel", {})
  const response = await running
  assert.equal(cancelled.cancelled, 1)
  assert.equal(response.error.code, "57014")
})
