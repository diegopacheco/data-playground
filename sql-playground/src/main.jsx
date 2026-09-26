import * as monaco from "monaco-editor"
import EditorWorker from "monaco-editor/editor/editor.worker.start?worker"
import { createRoot } from "react-dom/client"
import App from "./App.jsx"
import { registerCompletion } from "./sqlCompletion.js"
import "./styles.css"

self.MonacoEnvironment = { getWorker: () => new EditorWorker() }
monaco.editor.defineTheme("playground", {
  base: "vs",
  inherit: true,
  rules: [
    { token: "keyword", foreground: "1f5f99", fontStyle: "bold" },
    { token: "operator", foreground: "8a4b12" },
    { token: "string", foreground: "2f7d4f" },
    { token: "number", foreground: "b04a2a" },
    { token: "comment", foreground: "8b8f86", fontStyle: "italic" },
    { token: "predefined", foreground: "7a3fa0" }
  ],
  colors: {
    "editor.background": "#fffefb",
    "editor.lineHighlightBackground": "#f3f1ea",
    "editorLineNumber.foreground": "#b3b5ad",
    "editorLineNumber.activeForeground": "#1f5f99",
    "editorGutter.background": "#faf8f2"
  }
})
registerCompletion(monaco)

createRoot(document.getElementById("root")).render(<App />)
