import { createServer } from "node:http";

export function plain(value) {
  return JSON.parse(JSON.stringify(value, (_, v) => (typeof v === "bigint" ? Number(v) : v)));
}

export function rows(result) {
  return result.rows.map((r) => Object.fromEntries(result.columns.map((c) => [c, typeof r[c] === "bigint" ? Number(r[c]) : r[c]])));
}

export function micros(start) {
  return Number(process.hrtime.bigint() - start) / 1000;
}

export function now() {
  return process.hrtime.bigint();
}

async function body(req) {
  const chunks = [];
  for await (const c of req) chunks.push(c);
  const text = Buffer.concat(chunks).toString();
  return text ? JSON.parse(text) : {};
}

export function serve(port, routes, fallback) {
  const server = createServer(async (req, res) => {
    const url = new URL(req.url, "http://local");
    const route = routes[`${req.method} ${url.pathname}`];
    const send = (status, payload, type = "application/json") => {
      const data = type === "application/json" ? JSON.stringify(plain(payload)) : payload;
      res.writeHead(status, { "Content-Type": type, "Content-Length": Buffer.byteLength(data) });
      res.end(data);
    };
    try {
      if (route) return send(200, await route(await body(req), url));
      if (fallback) return await fallback(req, url, send);
      send(404, { error: "not found" });
    } catch (e) {
      send(500, { error: `${e.code || e.name}: ${e.message}` });
    }
  });
  server.listen(port, "0.0.0.0", () => console.log(`listening on ${port}`));
  return server;
}

export async function call(base, path, payload, timeoutMs = 30000) {
  const res = await fetch(`${base}${path}`, {
    method: payload === undefined ? "GET" : "POST",
    headers: { "Content-Type": "application/json" },
    body: payload === undefined ? undefined : JSON.stringify(payload),
    signal: AbortSignal.timeout(timeoutMs),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
  return data;
}

export function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}
