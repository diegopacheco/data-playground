import { createClient } from "@libsql/client";
import { ALL_ROWS, digest } from "./data.js";
import { micros, now, rows, serve, sleep } from "./http.js";

const NAME = process.env.NAME;
const PRIMARY = process.env.PRIMARY_URL;
const INTERVAL = Number(process.env.SYNC_INTERVAL || "0");
const FILE = `/data/${NAME}.db`;

const state = { name: NAME, file: FILE, sync_mode: INTERVAL ? `periodic every ${INTERVAL}s` : "on demand", sync_interval_s: INTERVAL, opened_at: null, last_sync: null, syncs: 0, sync_errors: 0, writes: 0, write_errors: 0 };
const remote = createClient({ url: PRIMARY });
let local;

async function open() {
  for (let i = 0; i < 60; i++) {
    try {
      const config = { url: `file:${FILE}`, syncUrl: PRIMARY, readYourWrites: true };
      if (INTERVAL) config.syncInterval = INTERVAL;
      local = createClient(config);
      const r = await local.sync();
      state.opened_at = new Date().toISOString();
      state.last_sync = { ...r, at: state.opened_at, reason: "open" };
      return;
    } catch (e) {
      console.log(`open failed: ${e.message}`);
      await sleep(1000);
    }
  }
  throw new Error("could not open the embedded replica");
}

async function localDigest() {
  const start = now();
  try {
    const all = rows(await local.execute(ALL_ROWS));
    return { ...digest(all), read_us: micros(start) };
  } catch (e) {
    if (String(e.message).includes("no such table")) return { ...digest([]), read_us: micros(start) };
    throw e;
  }
}

async function timed(client, statement) {
  const start = now();
  const result = await client.execute(statement);
  return { rows: rows(result), us: micros(start) };
}

function stats(samples) {
  const s = [...samples].sort((a, b) => a - b);
  const pick = (p) => s[Math.min(s.length - 1, Math.floor(p * s.length))];
  const round = (v) => Math.round(v * 10) / 10;
  return { n: s.length, min: round(s[0]), p50: round(pick(0.5)), p95: round(pick(0.95)), p99: round(pick(0.99)), max: round(s[s.length - 1]), mean: round(s.reduce((a, b) => a + b, 0) / s.length) };
}

async function bench({ n = 300 }) {
  const ids = (await local.execute("SELECT id FROM notes")).rows.map((r) => Number(r.id));
  const statementFor = (i) => ({ sql: "SELECT id, author, cents FROM notes WHERE id = ?", args: [ids[i % ids.length]] });
  for (let i = 0; i < 20; i++) {
    await local.execute(statementFor(i));
    await remote.execute(statementFor(i));
  }
  const localUs = [];
  const remoteUs = [];
  const mismatches = [];
  for (let i = 0; i < n; i++) {
    const a = await timed(local, statementFor(i));
    const b = await timed(remote, statementFor(i));
    localUs.push(a.us);
    remoteUs.push(b.us);
    if (JSON.stringify(a.rows) !== JSON.stringify(b.rows)) mismatches.push(statementFor(i).args[0]);
  }
  return { name: NAME, local: stats(localUs), remote: stats(remoteUs), mismatches };
}

async function write({ sql, args = [] }) {
  const start = now();
  try {
    const r = await local.execute({ sql, args });
    state.writes++;
    return { rows_affected: r.rowsAffected, last_insert_rowid: r.lastInsertRowid, us: micros(start) };
  } catch (e) {
    state.write_errors++;
    throw e;
  }
}

async function sync() {
  const start = now();
  try {
    const r = await local.sync();
    state.syncs++;
    state.last_sync = { ...r, at: new Date().toISOString(), reason: "on demand", us: micros(start) };
    return state.last_sync;
  } catch (e) {
    state.sync_errors++;
    throw e;
  }
}

await open();
serve(Number(process.env.PORT || "8080"), {
  "GET /health": async () => ({ ok: true }),
  "GET /state": async () => ({ ...state, local: await localDigest() }),
  "GET /digest": localDigest,
  "POST /read": async ({ sql, args = [] }) => timed(local, { sql, args }),
  "POST /write": write,
  "POST /sync": sync,
  "POST /bench": bench,
});
