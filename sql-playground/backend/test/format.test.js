import assert from "node:assert/strict"
import { test } from "node:test"
import { formatDuration } from "../../src/format.js"

test("sub millisecond timings keep enough precision to compare index lookups", () => {
  assert.equal(formatDuration(0.042), "0.042 ms")
})

test("timings under a second stay in milliseconds", () => {
  assert.equal(formatDuration(7.456), "7.46 ms")
  assert.equal(formatDuration(142.37), "142.4 ms")
})

test("timings scale to seconds, minutes and hours so long queries stay readable", () => {
  assert.equal(formatDuration(1420), "1.42 s")
  assert.equal(formatDuration(252000), "4 m 12 s")
  assert.equal(formatDuration(3723000), "1 h 02 m")
})

test("a value just under a minute never prints as 60.00 s", () => {
  assert.equal(formatDuration(59999), "1 m 00 s")
})
