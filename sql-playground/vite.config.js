import { defineConfig } from "vite"
import react from "@vitejs/plugin-react"
import { readPorts } from "./backend/ports.js"

const ports = readPorts()

export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: ports.frontend,
    strictPort: true,
    proxy: { "/api": `http://127.0.0.1:${ports.backend}` }
  }
})
