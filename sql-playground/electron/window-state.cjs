const fs = require("node:fs")
const path = require("node:path")

const defaults = { width: 1480, height: 940 }

function stateFile(userData) {
  return path.join(userData, "window.json")
}

function readState(userData) {
  try {
    return { ...defaults, ...JSON.parse(fs.readFileSync(stateFile(userData), "utf8")) }
  } catch {
    return { ...defaults }
  }
}

function writeState(userData, window) {
  if (!window || window.isDestroyed()) return
  const bounds = window.restoreBounds || window.getNormalBounds()
  try {
    fs.mkdirSync(userData, { recursive: true })
    fs.writeFileSync(stateFile(userData), JSON.stringify({ ...bounds, fullScreen: window.isFullScreen(), maximized: Boolean(window.restoreBounds) }))
  } catch {
    return
  }
}

function visibleOn(displays, state) {
  if (typeof state.x !== "number" || typeof state.y !== "number") return false
  return displays.some(({ workArea }) => state.x < workArea.x + workArea.width && state.x + state.width > workArea.x && state.y < workArea.y + workArea.height && state.y + state.height > workArea.y)
}

function toggleMaximize(window, screen) {
  if (!window || window.isDestroyed() || window.isFullScreen()) return
  if (window.restoreBounds) {
    window.setBounds(window.restoreBounds, true)
    window.restoreBounds = null
    return
  }
  window.restoreBounds = window.getBounds()
  window.setBounds(screen.getDisplayMatching(window.getBounds()).workArea, true)
}

module.exports = { readState, writeState, visibleOn, toggleMaximize }
