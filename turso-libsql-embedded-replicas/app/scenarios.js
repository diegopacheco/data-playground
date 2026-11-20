import { createClient } from "@libsql/client";
import { ALL_ROWS, SCHEMA, SEEDED, digest, insert, notes, ops, statement } from "./data.js";
import { call, rows, sleep } from "./http.js";

const PRIMARY = process.env.PRIMARY_URL;
export const REPLICAS = process.env.REPLICA_URLS.split(",").map((pair) => {
  const [name, url] = pair.split("=");
  return { name, url };
});
const primary = createClient({ url: PRIMARY });
const BY_ID = "SELECT id, author, cents FROM notes WHERE id = ?";

async function primaryDigest() {
  return digest(rows(await primary.execute(ALL_ROWS)));
}

async function waitFor(replica, target, timeoutMs = 15000) {
  const start = Date.now();
  let polls = 0;
  while (true) {
    const d = await call(replica.url, "/digest");
    polls++;
    if (d.sha === target.sha) return { digest: d, waited_ms: Date.now() - start, polls };
    if (Date.now() - start > timeoutMs) throw new Error(`${replica.name} did not converge in ${timeoutMs} ms`);
    await sleep(100);
  }
}

async function converge(target) {
  const out = [];
  for (const r of REPLICAS) {
    const state = await call(r.url, "/state");
    if (state.sync_interval_s) {
      out.push({ name: r.name, mode: state.sync_mode, sync: null, ...(await waitFor(r, target)) });
    } else {
      const sync = await call(r.url, "/sync", {});
      out.push({ name: r.name, mode: state.sync_mode, sync, digest: await call(r.url, "/digest"), waited_ms: 0 });
    }
  }
  return out;
}

async function reset() {
  await primary.batch([...SCHEMA, ...notes(SEEDED).map(insert)], "write");
  const target = await primaryDigest();
  return { seeded: SEEDED, primary: target, replicas: await converge(target) };
}

async function cents(replica, id) {
  const r = await call(replica.url, "/read", { sql: BY_ID, args: [id] });
  return { cents: r.rows[0]?.cents ?? null, us: r.us };
}

async function replication() {
  return reset();
}

async function writes() {
  await reset();
  const [r1, r2, r3] = REPLICAS;
  const t0 = Date.now();
  const timeline = [];
  const mark = (replica, action, detail) => timeline.push({ t_ms: Date.now() - t0, replica, action, ...detail });
  const fresh = notes(SEEDED + 10).slice(SEEDED);
  const writeUs = [];
  for (const row of fresh) writeUs.push((await call(r1.url, "/write", insert(row))).us);
  mark(r1.name, `${fresh.length} inserts forwarded to the primary`, { ids: fresh.map((x) => x.id) });
  const own = await call(r1.url, "/digest");
  const lastRow = (await call(r1.url, "/read", { sql: BY_ID, args: [fresh.at(-1).id] })).rows;
  mark(r1.name, "local read right after its own writes, no sync call", { count: own.count });
  const onPrimary = await primaryDigest();
  mark("primary", "count on the primary", { count: onPrimary.count });
  const r3First = await call(r3.url, "/digest");
  mark(r3.name, "local read before its periodic sync ran", { count: r3First.count });
  const stale = await call(r2.url, "/digest");
  mark(r2.name, "local read, never synced since the writes", { count: stale.count });
  const r2Sync = await call(r2.url, "/sync", {});
  mark(r2.name, "sync on demand", { frames_synced: r2Sync.frames_synced, frame_no: r2Sync.frame_no });
  const synced = await call(r2.url, "/digest");
  mark(r2.name, "local read after sync", { count: synced.count });
  const periodic = await waitFor(r3, onPrimary);
  mark(r3.name, "periodic sync caught up without any call", { count: periodic.digest.count, waited_ms: periodic.waited_ms });
  const before = await cents(r1, 1);
  const update = await call(r2.url, "/write", { sql: "UPDATE notes SET cents = cents + 1000 WHERE id = 1" });
  mark(r2.name, "update note 1 cents + 1000, forwarded", { rows_affected: update.rows_affected });
  const r2Sees = await cents(r2, 1);
  mark(r2.name, "reads its own update", { cents: r2Sees.cents });
  const r1Stale = await cents(r1, 1);
  mark(r1.name, "still reads the old value", { cents: r1Stale.cents });
  const r1Sync = await call(r1.url, "/sync", {});
  const r1Fresh = await cents(r1, 1);
  mark(r1.name, "reads the new value after sync", { cents: r1Fresh.cents, frames_synced: r1Sync.frames_synced });
  return {
    inserted_ids: fresh.map((x) => x.id),
    write_us: writeUs,
    read_your_writes: { count: own.count, last_row: lastRow[0] ?? null },
    primary: onPrimary,
    stale: { name: r2.name, count: stale.count, sha: stale.sha },
    after_sync: { name: r2.name, count: synced.count, sha: synced.sha, sync: r2Sync },
    periodic: { name: r3.name, first_count: r3First.count, count: periodic.digest.count, sha: periodic.digest.sha, waited_ms: periodic.waited_ms },
    update: { id: 1, before: before.cents, writer: r2.name, writer_sees: r2Sees.cents, other: r1.name, other_before_sync: r1Stale.cents, other_after_sync: r1Fresh.cents },
    timeline,
  };
}

async function latency() {
  await reset();
  const out = [];
  for (const r of REPLICAS) out.push(await call(r.url, "/bench", { n: 300 }, 120000));
  return { replicas: out };
}

async function consistency() {
  await reset();
  const list = ops(60, REPLICAS.length);
  const counts = { insert: 0, update: 0, delete: 0 };
  let affected = 0;
  for (const op of list) {
    const r = await call(REPLICAS[op.replica].url, "/write", statement(op));
    counts[op.kind]++;
    affected += r.rows_affected;
  }
  const target = await primaryDigest();
  return { ops: list.length, by_kind: counts, rows_affected: affected, primary: target, replicas: await converge(target) };
}

async function attempt(fn) {
  const start = Date.now();
  try {
    const value = await fn();
    return { ok: true, value, ms: Date.now() - start };
  } catch (e) {
    return { ok: false, error: e.message, ms: Date.now() - start };
  }
}

async function retry(fn, timeoutMs = 30000) {
  const start = Date.now();
  while (true) {
    try {
      return await fn();
    } catch (e) {
      if (Date.now() - start > timeoutMs) throw e;
      await sleep(500);
    }
  }
}

const outage = {};

async function outageBefore() {
  for (const k of Object.keys(outage)) delete outage[k];
  outage.before = await reset();
  return outage.before;
}

async function outageDuring() {
  const [r1, r2] = REPLICAS;
  const reads = [];
  for (const r of REPLICAS) reads.push({ name: r.name, ...(await attempt(() => call(r.url, "/digest"))) });
  outage.during = {
    primary_read: await attempt(primaryDigest),
    reads,
    write: { name: r1.name, ...(await attempt(() => call(r1.url, "/write", insert(notes(SEEDED + 1).at(-1)), 20000))) },
    sync: { name: r2.name, ...(await attempt(() => call(r2.url, "/sync", {}, 20000))) },
  };
  return outage.during;
}

async function outageAfter() {
  const [r1, r2, r3] = REPLICAS;
  const back = Date.now();
  await retry(primaryDigest);
  const fresh = notes(SEEDED + 7).slice(SEEDED);
  for (const row of fresh) {
    await retry(async () => {
      const found = (await call(r1.url, "/read", { sql: BY_ID, args: [row.id] })).rows.length;
      if (!found) await call(r1.url, "/write", insert(row), 20000);
    });
  }
  const own = await call(r1.url, "/digest");
  const target = await primaryDigest();
  const stale = await call(r2.url, "/digest");
  const sync = await retry(() => call(r2.url, "/sync", {}, 20000));
  const caught = await call(r2.url, "/digest");
  const periodic = await waitFor(r3, target, 30000);
  outage.after = {
    recovered_ms: Date.now() - back,
    inserted_ids: fresh.map((x) => x.id),
    writer: { name: r1.name, count: own.count, sha: own.sha },
    primary: target,
    stale: { name: r2.name, count: stale.count, sha: stale.sha },
    caught_up: { name: r2.name, count: caught.count, sha: caught.sha, sync },
    periodic: { name: r3.name, count: periodic.digest.count, sha: periodic.digest.sha, waited_ms: periodic.waited_ms },
  };
  return outage.after;
}

export async function topology() {
  const up = await attempt(async () => {
    const res = await fetch(`${PRIMARY}/version`, { signal: AbortSignal.timeout(2000) });
    return (await res.text()).trim();
  });
  const count = up.ok ? await attempt(primaryDigest) : null;
  const replicas = [];
  for (const r of REPLICAS) replicas.push({ name: r.name, ...(await attempt(() => call(r.url, "/state", undefined, 3000))) });
  return { primary: { url: PRIMARY, up: up.ok, version: up.value, error: up.error, digest: count?.value, digest_error: count?.error }, replicas };
}

export function outageResult() {
  return outage;
}

export const SCENARIOS = { replication, writes, latency, consistency };
export const OUTAGE = { before: outageBefore, during: outageDuring, after: outageAfter };
