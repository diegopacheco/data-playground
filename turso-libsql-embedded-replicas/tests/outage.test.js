import { test } from "node:test";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { SEEDED, digest, notes } from "../app/data.js";

const PORTS = Object.fromEntries(readFileSync(new URL("../scripts/ports.env", import.meta.url), "utf8").split("\n").filter((l) => l.includes("=")).map((l) => l.trim().split("=")));
const UI = `http://localhost:${PORTS.ui}`;
const PRIMARY = `http://localhost:${PORTS.primary}`;
const VICTIM = "t6-sqld";
const strip = ({ count, cents, max_id, sha }) => ({ count, cents, max_id, sha });

async function phase(name) {
  const res = await fetch(`${UI}/api/outage/${name}`, { method: "POST", signal: AbortSignal.timeout(120000) });
  const body = await res.json();
  assert.equal(res.status, 200, body.error);
  return body;
}

async function primaryUp(timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      if ((await fetch(`${PRIMARY}/health`, { signal: AbortSignal.timeout(2000) })).ok) return true;
    } catch {}
    await new Promise((r) => setTimeout(r, 1000));
  }
  return false;
}

const podman = (...args) => execFileSync("podman", args, { stdio: "pipe" });

test("replicas keep serving reads while the primary is down and catch up when it returns", async () => {
  const seeded = digest(notes(SEEDED));
  const before = await phase("before");
  for (const x of before.replicas) assert.deepEqual(strip(x.digest), seeded, `${x.name} must be in sync before the outage`);

  podman("stop", "-t", "5", VICTIM);
  let during;
  try {
    during = await phase("during");
  } finally {
    podman("start", VICTIM);
  }
  assert.equal(during.primary_read.ok, false, "the primary is stopped, a remote read must fail");
  for (const x of during.reads) {
    assert.equal(x.ok, true, `${x.name} must answer reads from its local file: ${x.error}`);
    assert.deepEqual(strip(x.value), seeded, `${x.name} must serve the last synced snapshot`);
  }
  assert.equal(during.write.ok, false, "writes are forwarded to the primary, so they must fail while it is down");
  assert.equal(during.sync.ok, false, "sync must fail while the primary is down");

  assert.ok(await primaryUp(60000), "the primary did not come back");
  const after = await phase("after");
  const expected = digest(notes(SEEDED + 7));
  assert.deepEqual(strip(after.primary), expected, "the primary keeps the seeded rows on its volume and gets the 7 new ones");
  assert.equal(after.writer.sha, expected.sha, "the writing replica reads its own writes");
  assert.equal(after.stale.sha, seeded.sha, "replica-2 has not synced yet, it still serves the pre outage snapshot");
  assert.ok(after.caught_up.sync.frames_synced >= 7, "the catch up sync must bring the 7 missed inserts");
  assert.equal(after.caught_up.sha, expected.sha);
  assert.equal(after.periodic.sha, expected.sha, "the periodic replica resumes syncing on its own");
});
