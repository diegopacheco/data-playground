import { readFileSync } from "node:fs";
import { OUTAGE, SCENARIOS, outageResult, topology } from "./scenarios.js";
import { serve } from "./http.js";

const PAGE = new URL("./index.html", import.meta.url);
const RESULTS = {};
let queue = Promise.resolve();

function exclusive(fn) {
  const run = queue.then(fn);
  queue = run.catch(() => {});
  return run;
}

async function run(name) {
  const result = await SCENARIOS[name]();
  result.ran_at = new Date().toISOString();
  RESULTS[name] = result;
  return result;
}

const routes = {
  "GET /api/results": async () => ({ ...RESULTS, outage: outageResult() }),
  "GET /api/topology": topology,
  "POST /api/run-all": () => exclusive(async () => {
    for (const name of Object.keys(SCENARIOS)) await run(name);
    return RESULTS;
  }),
};
for (const name of Object.keys(SCENARIOS)) routes[`POST /api/run/${name}`] = () => exclusive(() => run(name));
for (const [phase, fn] of Object.entries(OUTAGE)) routes[`POST /api/outage/${phase}`] = () => exclusive(fn);

serve(Number(process.env.PORT || "8080"), routes, async (req, url, send) => {
  if (req.method === "GET" && url.pathname === "/") return send(200, readFileSync(PAGE), "text/html; charset=utf-8");
  send(404, { error: "not found" });
});
