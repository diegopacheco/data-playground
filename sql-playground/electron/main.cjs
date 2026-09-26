const { app, BrowserWindow, ipcMain, nativeTheme, screen, shell } = require("electron")
const path = require("node:path")
const { buildMenu, capture } = require("./menu.cjs")
const { projectRoot, readPorts, portOpen, seedStatus, runScript } = require("./services.cjs")
const { readState, toggleMaximize, visibleOn, writeState } = require("./window-state.cjs")

const icon = path.join(__dirname, "..", "assets", "icon.png")
let window = null
let root = ""
let stopping = false
let stopped = false

function send(message) {
  if (window && !window.isDestroyed()) window.webContents.send("boot:status", message)
}

function createWindow() {
  const userData = app.getPath("userData")
  const saved = readState(userData)
  const placed = visibleOn(screen.getAllDisplays(), saved)
  window = new BrowserWindow({
    width: saved.width,
    height: saved.height,
    ...(placed ? { x: saved.x, y: saved.y } : {}),
    minWidth: 1100,
    minHeight: 700,
    show: false,
    backgroundColor: "#f4f2ec",
    title: "SQL Playground",
    titleBarStyle: "hiddenInset",
    trafficLightPosition: { x: 18, y: 20 },
    icon,
    webPreferences: { preload: path.join(__dirname, "preload.cjs"), contextIsolation: true, nodeIntegration: false, sandbox: true }
  })
  if (saved.maximized && placed) toggleMaximize(window, screen)
  if (saved.fullScreen) window.setFullScreen(true)
  window.once("ready-to-show", () => window.show())
  for (const event of ["resize", "move", "enter-full-screen", "leave-full-screen"]) window.on(event, () => writeState(userData, window))
  for (const [event, value] of [["enter-full-screen", true], ["leave-full-screen", false]]) window.on(event, () => window.webContents.send("window:fullscreen", value))
  window.on("close", () => writeState(userData, window))
  window.on("closed", () => {
    window = null
  })
  window.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url)
    return { action: "deny" }
  })
  window.loadFile(path.join(__dirname, "boot.html"))
  window.webContents.once("did-finish-load", () => boot())
}

function wait(ms) {
  return new Promise(resolve => setTimeout(resolve, ms))
}

async function boot() {
  root = projectRoot(app.isPackaged)
  if (!root) {
    send({ kind: "error", message: "The project folder is unknown. Run ./install.sh from the repository." })
    return
  }
  const ports = readPorts(root)
  send({
    kind: "plan",
    services: [
      { id: "postgres", label: "PostgreSQL 18", detail: `podman, port ${ports.postgres}, data in tmp/pgdata` },
      { id: "backend", label: "API", detail: `node, port ${ports.backend}` },
      { id: "seed", label: "Database", detail: "5M row dataset and 8 problem schemas" },
      { id: "frontend", label: "UI", detail: `vite, port ${ports.frontend}` }
    ]
  })
  for (const id of ["postgres", "backend", "seed", "frontend"]) send({ kind: "status", id, state: "starting" })
  let scriptCode = null
  runScript(root, "start-all.sh", line => send({ kind: "log", line })).then(code => {
    scriptCode = code
  })
  while (window && !window.isDestroyed() && !stopping) {
    const [postgres, backend, frontend] = await Promise.all([portOpen(ports.postgres), portOpen(ports.backend), portOpen(ports.frontend)])
    if (postgres) send({ kind: "status", id: "postgres", state: "ready" })
    if (backend) send({ kind: "status", id: "backend", state: "ready" })
    if (frontend) send({ kind: "status", id: "frontend", state: "ready" })
    const seed = backend ? await seedStatus(ports.backend) : null
    if (seed?.phase === "seeding") send({ kind: "status", id: "seed", state: "starting", note: `step ${seed.step}/${seed.total}` })
    if (seed?.phase === "ready") send({ kind: "status", id: "seed", state: "ready" })
    if (seed?.phase === "error") {
      send({ kind: "status", id: "seed", state: "failed" })
      send({ kind: "error", message: seed.error })
      return
    }
    if (scriptCode !== null && scriptCode !== 0) {
      send({ kind: "error", message: `start-all.sh failed. Logs: ${path.join(root, ".run", "logs")}` })
      return
    }
    if (frontend && seed?.phase === "ready") {
      window.loadURL(`http://localhost:${ports.frontend}`)
      return
    }
    await wait(1000)
  }
}

if (!app.requestSingleInstanceLock()) {
  app.quit()
} else {
  app.on("second-instance", () => {
    if (!window) return
    if (window.isMinimized()) window.restore()
    window.show()
    window.focus()
  })

  ipcMain.on("window:toggle-maximize", () => toggleMaximize(window, screen))
  ipcMain.handle("window:capture", () => capture())

  app.whenReady().then(() => {
    nativeTheme.themeSource = "light"
    if (process.platform === "darwin" && app.dock) app.dock.setIcon(icon)
    buildMenu(() => window)
    createWindow()
    app.on("activate", () => {
      if (window) window.show()
      else createWindow()
    })
  })

  app.on("window-all-closed", () => app.quit())

  app.on("before-quit", event => {
    if (stopped || !root) return
    event.preventDefault()
    if (stopping) return
    stopping = true
    if (window) writeState(app.getPath("userData"), window)
    runScript(root, "stop-all.sh", () => {}).finally(() => {
      stopped = true
      app.quit()
    })
  })
}
