const { Menu } = require("electron")
const { execFile } = require("node:child_process")

function capture() {
  return new Promise(resolve => execFile("/usr/sbin/screencapture", ["-i", "-c"], () => resolve("clipboard")))
}

function toggleFullScreen(window) {
  if (window) window.setFullScreen(!window.isFullScreen())
}

function buildMenu(getWindow) {
  Menu.setApplicationMenu(Menu.buildFromTemplate([
    { role: "appMenu" },
    { role: "editMenu" },
    {
      label: "View",
      submenu: [
        { role: "resetZoom", accelerator: "Command+Shift+0" },
        { role: "zoomIn", accelerator: "Command+Plus" },
        { role: "zoomIn", accelerator: "Command+=", visible: false },
        { role: "zoomOut", accelerator: "Command+-" },
        { type: "separator" },
        { label: "Capture Screenshot", accelerator: "Command+P", click: () => capture() },
        { label: "Toggle Full Screen", accelerator: "Command+Shift+Return", click: () => toggleFullScreen(getWindow()) },
        { type: "separator" },
        { role: "reload" },
        { role: "toggleDevTools" }
      ]
    },
    { role: "windowMenu" }
  ]))
}

module.exports = { buildMenu, capture, toggleFullScreen }
