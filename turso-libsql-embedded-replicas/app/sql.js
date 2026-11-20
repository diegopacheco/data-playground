import { createInterface } from "node:readline";
import { createClient } from "@libsql/client";
import { rows } from "./http.js";

const primary = createClient({ url: process.env.PRIMARY_URL });
const input = createInterface({ input: process.stdin, output: process.stdout, prompt: "sqld> ", terminal: process.stdin.isTTY });

let open = true;
input.on("close", () => (open = false));
input.prompt();
for await (const line of input) {
  const sql = line.trim();
  if (sql) {
    try {
      const result = await primary.execute(sql);
      if (result.columns.length) console.table(rows(result));
      else console.log(`rows affected: ${result.rowsAffected}`);
    } catch (e) {
      console.log(`error: ${e.message}`);
    }
  }
  if (open) input.prompt();
}
