import assert from "node:assert/strict"
import { test } from "node:test"
import { firstKeyword, isSingleStatement, normalize } from "../query.js"

test("a DO block with inner semicolons is one statement, so it is explained and timed as one", () => {
  assert.equal(isSingleStatement("DO $$ BEGIN PERFORM 1; PERFORM 2; END $$"), true)
})

test("semicolons inside string literals do not split a statement", () => {
  assert.equal(isSingleStatement("select 'a;b' as x"), true)
})

test("two statements are detected so the plan is skipped instead of failing", () => {
  assert.equal(isSingleStatement(normalize("create table x(a int); select 1;")), false)
})

test("the leading keyword ignores comments, which decides cursor versus plain execution", () => {
  assert.equal(firstKeyword("-- note\n/* c */ WITH x AS (select 1) select * from x"), "with")
})
