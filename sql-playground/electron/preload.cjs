const { contextBridge, ipcRenderer } = require("electron")

contextBridge.exposeInMainWorld("sqlPlayground", {
  toggleMaximize: () => ipcRenderer.send("window:toggle-maximize"),
  capture: () => ipcRenderer.invoke("window:capture"),
  onBoot: listener => ipcRenderer.on("boot:status", (_event, status) => listener(status)),
  onFullscreen: listener => {
    const handler = (_event, value) => listener(value)
    ipcRenderer.on("window:fullscreen", handler)
    return () => ipcRenderer.removeListener("window:fullscreen", handler)
  }
})
