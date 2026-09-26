import pg from "pg"
import { readPorts } from "./ports.js"

const ports = readPorts()

export const connection = {
  host: "localhost",
  port: ports.postgres,
  user: "playground",
  password: "playground",
  database: "playground"
}

export const rawText = { getTypeParser: () => value => value }

export function createPool() {
  const pool = new pg.Pool({ ...connection, max: 12 })
  pool.on("error", () => {})
  return pool
}

export async function connectClient() {
  const client = new pg.Client(connection)
  client.on("error", () => {})
  await client.connect()
  return client
}
