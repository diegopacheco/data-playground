import assert from "node:assert/strict"
import { test } from "node:test"
import { filterColumns, hintsFor } from "../hints.js"

const orders = { "shop.orders": { rows: 1500000, columns: ["id", "customer_id", "status", "created_at", "total"], indexed: ["id", "customer_id", "created_at"] } }

function seqScan(filter, planRows, extra = {}) {
  return { Plan: { "Node Type": "Seq Scan", "Relation Name": "orders", Schema: "shop", Alias: "o", "Plan Rows": planRows, Filter: filter, ...extra } }
}

test("a selective filter on an unindexed column asks for an index on that exact column", () => {
  const hints = hintsFor({ sql: "select id from shop.orders where status = 'pending'", plan: seqScan("(o.status = 'pending'::text)", 90000), facts: orders })
  const critical = hints.find(hint => hint.level === "critical")
  assert.ok(critical, "expected a critical hint for a 1.5M row sequential scan")
  assert.equal(critical.fix, "CREATE INDEX ON shop.orders (status);")
})

test("an index is never suggested for a column that already has one", () => {
  const hints = hintsFor({ sql: "select id from shop.orders where customer_id = 7", plan: seqScan("(o.customer_id = 7)", 6), facts: orders })
  assert.ok(!hints.some(hint => hint.fix?.startsWith("CREATE INDEX")))
  assert.ok(hints.some(hint => hint.title.includes("was not chosen")))
})

test("a filter that keeps most of the table does not push an index that would not help", () => {
  const hints = hintsFor({ sql: "select id from shop.orders where status = 'delivered'", plan: seqScan("(o.status = 'delivered'::text)", 1050000), facts: orders })
  assert.ok(!hints.some(hint => hint.level === "critical"))
  assert.ok(hints.some(hint => hint.title.startsWith("Filter keeps")))
})

test("wrapping an indexed column in a cast recommends an expression index or a range", () => {
  const hints = hintsFor({ sql: "select id from shop.orders where created_at::date = '2024-03-01'", plan: seqScan("((o.created_at)::date = '2024-03-01'::date)", 900), facts: orders })
  const warning = hints.find(hint => hint.title.includes("blocks index use"))
  assert.equal(warning.fix, "CREATE INDEX ON shop.orders ((created_at::date));")
})

test("row estimates below a LIMIT are not reported as misestimates", () => {
  const plan = { Plan: { "Node Type": "Limit", "Plan Rows": 5, "Actual Rows": 5, "Actual Loops": 1, Plans: [{ "Node Type": "Sort", "Plan Rows": 5000000, "Actual Rows": 5, "Actual Loops": 1, "Sort Key": ["unit_price DESC"], Plans: [] }] } }
  const hints = hintsFor({ sql: "select id from t order by unit_price desc limit 5", plan, analyzed: true, facts: {} })
  assert.ok(!hints.some(hint => hint.title.startsWith("Row estimate")))
})

test("a real misestimate outside a LIMIT is reported with the table to analyze", () => {
  const plan = seqScan("(o.total > 10::numeric)", 100, { "Actual Rows": 800000, "Actual Loops": 1, "Rows Removed by Filter": 700000 })
  const hints = hintsFor({ sql: "select id from shop.orders where total > 10", plan, analyzed: true, facts: orders })
  assert.ok(hints.some(hint => hint.title.startsWith("Row estimate") && hint.fix === "ANALYZE shop.orders;"))
})

test("disk sorts and hash batches point at work_mem", () => {
  const plan = { Plan: { "Node Type": "Hash Join", "Plan Rows": 10, Plans: [{ "Node Type": "Sort", "Sort Space Type": "Disk", "Sort Space Used": 51200, "Sort Key": ["total"], "Plan Rows": 1 }, { "Node Type": "Hash", "Hash Batches": 8, "Plan Rows": 1 }] } }
  const hints = hintsFor({ sql: "select 1", plan, facts: {} })
  assert.equal(hints.filter(hint => hint.fix === "SET work_mem = '64MB';").length, 2)
})

test("SQL anti patterns are flagged even when the plan looks fine", () => {
  const hints = hintsFor({ sql: "select * from shop.customers where email like '%gmail.com' and id not in (select customer_id from shop.orders) offset 5000", plan: null, facts: { "shop.customers": { rows: 250000, columns: ["id", "email"], indexed: ["id"] } } })
  const titles = hints.map(hint => hint.title)
  assert.ok(titles.includes("SELECT * reads every column"))
  assert.ok(titles.includes("OFFSET 5,000 discards rows"))
  assert.ok(titles.includes("NOT IN with a subquery"))
  assert.ok(hints.some(hint => hint.fix === "CREATE INDEX ON shop.customers USING gin (email gin_trgm_ops);"))
})

test("filter parsing ignores literals and keeps only real columns", () => {
  const parsed = filterColumns("((o.status = 'status'::text) AND (lower(o.status) = 'x'::text))", ["status"])
  assert.deepEqual(parsed.expressions, [{ fn: "lower", column: "status" }])
})

test("hints are ordered from the most to the least severe", () => {
  const hints = hintsFor({ sql: "select * from shop.orders where status = 'pending'", plan: seqScan("(o.status = 'pending'::text)", 90000), facts: orders })
  const order = { critical: 0, warning: 1, info: 2, good: 3 }
  assert.deepEqual(hints.map(hint => order[hint.level]), [...hints.map(hint => order[hint.level])].sort())
})
