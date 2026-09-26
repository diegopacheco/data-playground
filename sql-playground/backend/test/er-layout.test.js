import assert from "node:assert/strict"
import { test } from "node:test"
import { layout, overlaps } from "../../src/erLayout.js"

const column = name => ({ name, type: "int" })
const table = (name, columns, refs = []) => ({ name, columns: columns.map(column), foreignKeys: refs.map(([col, target]) => ({ name: `${name}_${col}`, columns: [col], table: target, refColumns: ["id"] })) })

const tables = [
  table("categories", ["id", "parent_id", "name"], [["parent_id", "categories"]]),
  table("customers", ["id", "email", "name", "country"]),
  table("products", ["id", "category_id", "name"], [["category_id", "categories"]]),
  table("orders", ["id", "customer_id", "status"], [["customer_id", "customers"]]),
  table("order_items", ["id", "order_id", "product_id"], [["order_id", "orders"], ["product_id", "products"]]),
  table("payments", ["id", "order_id"], [["order_id", "orders"]]),
  table("reviews", ["id", "product_id", "customer_id"], [["product_id", "products"], ["customer_id", "customers"]])
]

test("no two tables of the ER diagram overlap", () => {
  const boxes = [...layout(tables).positions.values()]
  for (let i = 0; i < boxes.length; i++) {
    for (let j = i + 1; j < boxes.length; j++) assert.equal(overlaps(boxes[i], boxes[j]), false)
  }
})

test("a referenced table is drawn left of every table that points to it, so arrows read left to right", () => {
  const { positions } = layout(tables)
  for (const source of tables) {
    for (const fk of source.foreignKeys) {
      if (fk.table === source.name) continue
      assert.ok(positions.get(fk.table).x < positions.get(source.name).x, `${fk.table} should be left of ${source.name}`)
    }
  }
})

test("a self reference does not push a table into its own next column", () => {
  const { positions } = layout(tables)
  assert.equal(positions.get("categories").x, positions.get("customers").x)
})
