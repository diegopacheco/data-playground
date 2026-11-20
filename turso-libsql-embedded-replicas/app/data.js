import { createHash } from "node:crypto";

export const AUTHORS = ["ana", "bo", "cy", "dee"];
export const SEEDED = 100;

function random(seed) {
  let s = seed >>> 0;
  return () => {
    s = (Math.imul(s, 1664525) + 1013904223) >>> 0;
    return s / 4294967296;
  };
}

export function notes(count, seed = 6) {
  const r = random(seed);
  const rows = [];
  for (let id = 1; id <= count; id++) {
    rows.push({ id, author: AUTHORS[Math.floor(r() * AUTHORS.length)], cents: 100 + Math.floor(r() * 49900) });
  }
  return rows;
}

export function ops(count, replicas, seed = 66) {
  const r = random(seed);
  const kinds = ["insert", "update", "delete"];
  let next = SEEDED + 1;
  const out = [];
  for (let i = 0; i < count; i++) {
    const kind = kinds[Math.floor(r() * kinds.length)];
    const replica = i % replicas;
    if (kind === "insert") {
      out.push({ replica, kind, id: next++, author: AUTHORS[Math.floor(r() * AUTHORS.length)], cents: 100 + Math.floor(r() * 49900) });
    } else {
      out.push({ replica, kind, id: 1 + Math.floor(r() * (next - 1)), cents: 100 + Math.floor(r() * 49900) });
    }
  }
  return out;
}

export function digest(rows) {
  const sorted = [...rows].sort((a, b) => a.id - b.id);
  const text = sorted.map((x) => `${x.id}|${x.author}|${x.cents}`).join("\n");
  return {
    count: sorted.length,
    cents: sorted.reduce((s, x) => s + x.cents, 0),
    max_id: sorted.length ? sorted[sorted.length - 1].id : 0,
    sha: createHash("sha256").update(text).digest("hex").slice(0, 16),
  };
}

export const SCHEMA = [
  "DROP TABLE IF EXISTS notes",
  "CREATE TABLE notes (id INTEGER PRIMARY KEY, author TEXT NOT NULL, cents INTEGER NOT NULL)",
];

export const ALL_ROWS = "SELECT id, author, cents FROM notes ORDER BY id";

export function insert(row) {
  return { sql: "INSERT INTO notes (id, author, cents) VALUES (?, ?, ?)", args: [row.id, row.author, row.cents] };
}

export function statement(op) {
  if (op.kind === "insert") return insert(op);
  if (op.kind === "update") return { sql: "UPDATE notes SET cents = ? WHERE id = ?", args: [op.cents, op.id] };
  return { sql: "DELETE FROM notes WHERE id = ?", args: [op.id] };
}
