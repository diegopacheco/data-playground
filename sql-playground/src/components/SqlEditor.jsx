import * as monaco from "monaco-editor"
import { useEffect, useRef } from "react"

export default function SqlEditor({ value, onChange, onRun, editorRef, readOnly = false, fontSize = 15 }) {
  const host = useRef(null)
  const runRef = useRef(onRun)
  const changeRef = useRef(onChange)
  const emitted = useRef(value)
  runRef.current = onRun
  changeRef.current = onChange

  useEffect(() => {
    const editor = monaco.editor.create(host.current, {
      value,
      language: "pgsql",
      theme: "playground",
      readOnly,
      automaticLayout: true,
      minimap: { enabled: false },
      fontFamily: "'SF Mono', 'JetBrains Mono', Menlo, monospace",
      fontSize,
      lineHeight: Math.round(fontSize * 1.6),
      lineNumbers: "on",
      lineNumbersMinChars: 3,
      padding: { top: 14, bottom: 14 },
      scrollBeyondLastLine: false,
      renderLineHighlight: "all",
      overviewRulerBorder: false,
      quickSuggestions: { other: true, comments: false, strings: false },
      suggestOnTriggerCharacters: true,
      wordBasedSuggestions: "off",
      tabSize: 2,
      fixedOverflowWidgets: true,
      editContext: false,
      scrollbar: { verticalScrollbarSize: 10, horizontalScrollbarSize: 10 }
    })
    editor.addAction({
      id: "playground-run",
      label: "Run query",
      keybindings: [monaco.KeyMod.CtrlCmd | monaco.KeyCode.Enter],
      run: () => runRef.current?.()
    })
    const subscription = editor.onDidChangeModelContent(() => {
      emitted.current = editor.getValue()
      changeRef.current?.(emitted.current)
    })
    if (editorRef) editorRef.current = editor
    return () => {
      subscription.dispose()
      editor.dispose()
      if (editorRef) editorRef.current = null
    }
  }, [])

  useEffect(() => {
    const editor = editorRef?.current
    if (!editor || value === emitted.current) return
    emitted.current = value
    editor.setValue(value)
  }, [value])

  return <div className="sql-editor" ref={host} />
}

export function runnableText(editor) {
  if (!editor) return ""
  const selection = editor.getSelection()
  const selected = selection && !selection.isEmpty() ? editor.getModel().getValueInRange(selection) : ""
  return selected.trim() ? selected : editor.getValue()
}

export function markError(editor, sql, position, message) {
  if (!editor) return
  const model = editor.getModel()
  if (!position) {
    monaco.editor.setModelMarkers(model, "playground", [])
    return
  }
  const selection = editor.getSelection()
  const base = selection && !selection.isEmpty() ? model.getOffsetAt(selection.getStartPosition()) : 0
  const start = model.getPositionAt(base + position - 1)
  const end = model.getPositionAt(base + position - 1 + Math.max(1, (sql.slice(position - 1).match(/^\w+/)?.[0] ?? " ").length))
  monaco.editor.setModelMarkers(model, "playground", [{
    severity: monaco.MarkerSeverity.Error,
    message,
    startLineNumber: start.lineNumber,
    startColumn: start.column,
    endLineNumber: end.lineNumber,
    endColumn: end.column
  }])
}

export function clearMarkers(editor) {
  if (editor) monaco.editor.setModelMarkers(editor.getModel(), "playground", [])
}

export function colorize(sql) {
  return monaco.editor.colorize(sql, "pgsql", { tabSize: 2 })
}
