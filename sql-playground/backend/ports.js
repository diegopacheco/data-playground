import { readFileSync } from "node:fs"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"

export const root = join(dirname(fileURLToPath(import.meta.url)), "..")

export function readPorts(file = join(root, "scripts", "ports.env")) {
  return Object.fromEntries(
    readFileSync(file, "utf8")
      .split("\n")
      .map(line => line.trim())
      .filter(line => line && !line.startsWith("#") && line.includes("="))
      .map(line => line.split("=").map(part => part.trim()))
      .map(([name, port]) => [name, Number(port)])
  )
}
