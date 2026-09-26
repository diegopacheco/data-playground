const { spawn } = require("node:child_process")
const fs = require("node:fs")
const http = require("node:http")
const net = require("node:net")
const os = require("node:os")
const path = require("node:path")

const configDir = path.join(os.homedir(), ".sql-playground")

function readConfig(name) {
  try {
    return fs.readFileSync(path.join(configDir, name), "utf8").trim()
  } catch {
    return ""
  }
}

function projectRoot(packaged) {
  return packaged ? readConfig("root") : path.join(__dirname, "..")
}

function environment() {
  const saved = readConfig("path")
  const extra = ["/opt/homebrew/bin", "/usr/local/bin", "/usr/bin", "/bin", "/usr/sbin", "/sbin"]
  return { ...process.env, PATH: [saved, process.env.PATH, ...extra].filter(Boolean).join(":") }
}

function readPorts(root) {
  return Object.fromEntries(fs.readFileSync(path.join(root, "scripts", "ports.env"), "utf8")
    .split("\n").map(line => line.trim()).filter(line => line.includes("=") && !line.startsWith("#"))
    .map(line => line.split("=").map(part => part.trim())).map(([name, port]) => [name, Number(port)]))
}

function portOpen(port) {
  return new Promise(resolve => {
    const socket = net.connect({ host: "127.0.0.1", port })
    socket.once("connect", () => {
      socket.destroy()
      resolve(true)
    })
    socket.once("error", () => resolve(false))
    socket.setTimeout(800, () => {
      socket.destroy()
      resolve(false)
    })
  })
}

function seedStatus(port) {
  return new Promise(resolve => {
    const request = http.get({ host: "127.0.0.1", port, path: "/api/status", timeout: 1500 }, response => {
      let body = ""
      response.on("data", chunk => {
        body += chunk
      })
      response.on("end", () => {
        try {
          resolve(JSON.parse(body))
        } catch {
          resolve(null)
        }
      })
    })
    request.on("error", () => resolve(null))
    request.on("timeout", () => {
      request.destroy()
      resolve(null)
    })
  })
}

function runScript(root, name, onLine) {
  return new Promise(resolve => {
    const child = spawn("/bin/bash", [path.join(root, "scripts", name)], { cwd: root, env: environment() })
    const forward = chunk => String(chunk).split("\n").filter(Boolean).forEach(onLine)
    child.stdout.on("data", forward)
    child.stderr.on("data", forward)
    child.on("close", code => resolve(code))
    child.on("error", error => {
      onLine(error.message)
      resolve(1)
    })
  })
}

module.exports = { projectRoot, readPorts, portOpen, seedStatus, runScript }
