import { before, describe, test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, rmSync } from "node:fs";
import { createClient } from "@libsql/client";
import { ALL_ROWS, SEEDED, digest, notes, ops } from "../app/data.js";
import { rows } from "../app/http.js";

const UI = process.env.UI_URL || "http://localhost:8080";
const PRIMARY = process.env.PRIMARY_URL;
const REPLICA_NAMES = process.env.REPLICA_URLS.split(",").map((p) => p.split("=")[0]);
const PERIODIC_S = 2;
const strip = ({ count, cents, max_id, sha }) => ({ count, cents, max_id, sha });

function model() {
  const table = new Map(notes(SEEDED).map((r) => [r.id, { ...r }]));
  let affected = 0;
  for (const op of ops(60, REPLICA_NAMES.length)) {
    if (op.kind === "insert") {
      table.set(op.id, { id: op.id, author: op.author, cents: op.cents });
      affected++;
    } else if (table.has(op.id)) {
      if (op.kind === "update") table.get(op.id).cents = op.cents;
      else table.delete(op.id);
      affected++;
    }
  }
  return { expected: digest([...table.values()]), affected };
}

let r;
before(async () => {
  r = await (await fetch(`${UI}/api/results`)).json();
  for (const name of ["replication", "writes", "latency", "consistency"]) assert.ok(r[name], `scenario ${name} has no result, run POST /api/run-all first`);
});

describe("replication from the primary", () => {
  test("every embedded replica holds exactly the seeded rows after its first sync", () => {
    const expected = digest(notes(SEEDED));
    assert.deepEqual(strip(r.replication.primary), expected);
    assert.deepEqual(r.replication.replicas.map((x) => x.name), REPLICA_NAMES);
    for (const x of r.replication.replicas) assert.deepEqual(strip(x.digest), expected, `${x.name} must equal the primary`);
  });

  test("a fresh embedded replica opened by the test bootstraps the same data as the primary", async () => {
    const dir = mkdtempSync("/tmp/replica-");
    const file = `${dir}/test.db`;
    const local = createClient({ url: `file:${file}`, syncUrl: PRIMARY });
    try {
      const sync = await local.sync();
      assert.ok(sync.frames_synced > 0, "a fresh replica must pull frames from the primary");
      const remote = createClient({ url: PRIMARY });
      const expected = digest(rows(await remote.execute(ALL_ROWS)));
      assert.deepEqual(digest(rows(await local.execute(ALL_ROWS))), expected);
      remote.close();
    } finally {
      local.close();
      rmSync(dir, { recursive: true, force: true });
    }
  });
});

describe("writes, read your writes and staleness", () => {
  const seeded = digest(notes(SEEDED));
  const afterInserts = digest(notes(SEEDED + 10));

  test("writes sent to an embedded replica are forwarded to the primary", () => {
    const w = r.writes;
    assert.deepEqual(w.inserted_ids, notes(SEEDED + 10).slice(SEEDED).map((x) => x.id));
    assert.deepEqual(strip(w.primary), afterInserts, "the primary must hold the 10 rows written through replica-1");
  });

  test("the writing replica reads its own writes without calling sync", () => {
    assert.equal(r.writes.read_your_writes.count, SEEDED + 10);
    assert.deepEqual(r.writes.read_your_writes.last_row, notes(SEEDED + 10).at(-1));
  });

  test("an on demand replica stays stale until it syncs, then matches the primary", () => {
    assert.equal(r.writes.stale.count, SEEDED);
    assert.equal(r.writes.stale.sha, seeded.sha, "before sync replica-2 must still serve the old snapshot");
    assert.ok(r.writes.after_sync.sync.frames_synced >= 10, "the 10 inserts must arrive as at least 10 frames");
    assert.equal(r.writes.after_sync.sha, afterInserts.sha);
  });

  test("a periodic replica converges within one sync interval without any call", () => {
    assert.equal(r.writes.periodic.sha, afterInserts.sha);
    assert.ok(r.writes.periodic.waited_ms <= PERIODIC_S * 1000 + 1500, `waited ${r.writes.periodic.waited_ms} ms with a ${PERIODIC_S}s interval`);
  });

  test("an update made on one replica is invisible on another until that one syncs", () => {
    const u = r.writes.update;
    const original = notes(SEEDED)[0].cents;
    assert.equal(u.before, original);
    assert.equal(u.writer_sees, original + 1000);
    assert.equal(u.other_before_sync, original, "replica-1 has not synced, it must return the old value");
    assert.equal(u.other_after_sync, original + 1000);
  });
});

describe("latency", () => {
  test("local reads take microseconds and are faster than remote reads to the primary", () => {
    for (const x of r.latency.replicas) {
      assert.equal(x.local.n, 300);
      assert.deepEqual(x.mismatches, [], `${x.name} local and remote rows must be identical`);
      assert.ok(x.local.p50 < 1000, `${x.name} local p50 ${x.local.p50} us must stay under 1 ms`);
      assert.ok(x.remote.p50 > x.local.p50 * 3, `${x.name} remote p50 ${x.remote.p50} us vs local ${x.local.p50} us`);
    }
  });
});

describe("consistency after mixed writes from every replica", () => {
  const { expected, affected } = model();

  test("the primary holds the result of applying every operation in order", async () => {
    assert.equal(r.consistency.ops, 60);
    assert.equal(r.consistency.rows_affected, affected, "update and delete of a missing id must affect 0 rows");
    assert.deepEqual(strip(r.consistency.primary), expected);
    const remote = createClient({ url: PRIMARY });
    assert.deepEqual(digest(rows(await remote.execute(ALL_ROWS))), expected, "reading the primary directly must give the same rows");
    remote.close();
  });

  test("every replica matches the primary after sync", () => {
    for (const x of r.consistency.replicas) assert.deepEqual(strip(x.digest), expected, `${x.name} diverged`);
  });
});

describe("ui", () => {
  test("the page has every tab", async () => {
    const html = await (await fetch(`${UI}/`)).text();
    for (const tab of ["replicas", "latency", "writes", "consistency", "outage"]) assert.ok(html.includes(`data-tab="${tab}"`), tab);
  });
});
