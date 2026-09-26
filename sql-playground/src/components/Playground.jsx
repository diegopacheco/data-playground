import { useEffect, useRef, useState } from "react"
import { api } from "../api.js"
import { compactCount, formatCount, formatDuration } from "../format.js"
import HintsView from "./HintsView.jsx"
import PlanView from "./PlanView.jsx"
import ResultTable from "./ResultTable.jsx"
import SqlEditor, { clearMarkers, markError, runnableText } from "./SqlEditor.jsx"

function SchemaTree({ catalog, onInsert, onPreview }) {
  const [open, setOpen] = useState({ shop: true })
  return (
    <aside className="schema-tree">
      <div className="side-title">Schemas</div>
      {catalog.schemas.map(schema => (
        <div key={schema.name} className="tree-schema">
          <button className="tree-toggle" onClick={() => setOpen({ ...open, [schema.name]: !open[schema.name] })}>
            <span className={`caret ${open[schema.name] ? "open" : ""}`} />{schema.name}<small>{schema.tables.length}</small>
          </button>
          {open[schema.name] && schema.tables.map(table => (
            <button
              key={table.name}
              className="tree-table"
              title={`${table.comment ?? ""}\nClick inserts the name, double click previews 100 rows.`}
              onClick={() => onInsert(`${schema.name}.${table.name}`)}
              onDoubleClick={() => onPreview(`SELECT *\nFROM ${schema.name}.${table.name}\nLIMIT 100;`)}
            >
              <span>{table.name}</span><small>{compactCount(table.rows)}</small>
            </button>
          ))}
        </div>
      ))}
    </aside>
  )
}

function Elapsed({ since }) {
  const [now, setNow] = useState(performance.now())
  useEffect(() => {
    const timer = setInterval(() => setNow(performance.now()), 100)
    return () => clearInterval(timer)
  }, [])
  return <>{formatDuration(now - since)}</>
}

export default function Playground({ catalog, sql, setSql, analyze, setAnalyze, runToken, editorRef, onCatalogChange }) {
  const [response, setResponse] = useState(null)
  const [running, setRunning] = useState(null)
  const [panel, setPanel] = useState("results")
  const [resultIndex, setResultIndex] = useState(0)
  const [split, setSplit] = useState(48)
  const lastRun = useRef("")
  const area = useRef(null)

  async function execute(text) {
    if (!text.trim() || running) return
    clearMarkers(editorRef.current)
    lastRun.current = text
    setRunning(performance.now())
    try {
      const data = await api.query(text, analyze)
      setResponse({ ...data, sql: text })
      setResultIndex(Math.max(0, (data.results?.length ?? 1) - 1))
      if (data.error) {
        setPanel("messages")
        markError(editorRef.current, text, data.error.position, data.error.message)
      } else if (panel === "messages") {
        setPanel("results")
      }
      if (/\b(create|drop|alter)\b/i.test(text)) onCatalogChange()
    } catch (error) {
      setResponse({ error: { message: error.message }, sql: text })
      setPanel("messages")
    } finally {
      setRunning(null)
    }
  }

  const run = () => execute(runnableText(editorRef.current))

  useEffect(() => {
    if (runToken) run()
  }, [runToken])

  async function applyFix(fix) {
    setRunning(performance.now())
    try {
      const data = await api.query(fix, false)
      if (data.error) {
        setResponse({ ...response, error: data.error })
        setPanel("messages")
        return
      }
      onCatalogChange()
    } finally {
      setRunning(null)
    }
    await execute(lastRun.current)
  }

  function insertFix(fix) {
    setSql(`${fix}\n\n${sql}`)
  }

  function insertAtCursor(text) {
    const editor = editorRef.current
    if (!editor) return
    editor.executeEdits("schema-tree", [{ range: editor.getSelection(), text, forceMoveMarkers: true }])
    editor.focus()
  }

  function startDrag(event) {
    event.preventDefault()
    const bounds = area.current.getBoundingClientRect()
    const move = moveEvent => setSplit(Math.min(80, Math.max(20, ((moveEvent.clientY - bounds.top) / bounds.height) * 100)))
    const stop = () => {
      window.removeEventListener("pointermove", move)
      window.removeEventListener("pointerup", stop)
    }
    window.addEventListener("pointermove", move)
    window.addEventListener("pointerup", stop)
  }

  const results = response?.results ?? []
  const current = results[resultIndex]
  const warnings = response?.hints?.filter(hint => hint.level === "critical" || hint.level === "warning").length ?? 0

  return (
    <div className="playground">
      <SchemaTree catalog={catalog} onInsert={insertAtCursor} onPreview={text => { setSql(text); setTimeout(() => execute(text), 0) }} />
      <section className="work-area" ref={area}>
        <div className="toolbar">
          <button className="primary-button" onClick={run} disabled={Boolean(running)}>
            <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M4 2.5v11l9-5.5z" /></svg>
            Run <kbd>⌘</kbd><kbd>↵</kbd>
          </button>
          {running && <button className="danger-button" onClick={() => api.cancel()}>Cancel <kbd>⌘</kbd><kbd>.</kbd></button>}
          <label className="switch" title="EXPLAIN ANALYZE runs the statement again inside a rolled back transaction to measure every node">
            <input type="checkbox" checked={analyze} onChange={event => setAnalyze(event.target.checked)} />
            <span />Analyze plan <kbd>⌘</kbd><kbd>E</kbd>
          </label>
          <div className="toolbar-spacer" />
          <div className={`timing ${running ? "live" : ""} ${response?.error ? "failed" : ""}`}>
            <small>{running ? "Running" : response?.error ? "Failed" : response ? "Ran in" : "Time"}</small>
            <strong>{running ? <Elapsed since={running} /> : response?.elapsedMs !== undefined ? formatDuration(response.elapsedMs) : "-"}</strong>
            {!running && response?.elapsedMs !== undefined && <span>{formatCount(response.elapsedMs)} ms</span>}
          </div>
          {!running && current && <div className="row-count"><strong>{formatCount(current.rowCount)}</strong><small>rows</small></div>}
        </div>
        <div className="editor-pane" style={{ height: `${split}%` }}>
          <SqlEditor value={sql} onChange={setSql} onRun={run} editorRef={editorRef} />
        </div>
        <div className="divider" onPointerDown={startDrag} onDoubleClick={() => setSplit(48)} />
        <div className="output-pane">
          <nav className="output-tabs">
            {[
              ["results", "Results", current ? formatCount(current.rowCount) : null],
              ["plan", "Query plan", response?.plan ? (response.analyzed ? "analyzed" : "estimated") : null],
              ["hints", "Hints", response?.hints ? String(warnings || response.hints.length) : null],
              ["messages", "Messages", response?.error ? "error" : response?.notices?.length ? String(response.notices.length) : null]
            ].map(([id, title, badge]) => (
              <button key={id} className={panel === id ? "active" : ""} onClick={() => setPanel(id)}>
                {title}{badge && <span className={`badge ${id === "hints" && warnings ? "alert" : ""} ${id === "messages" && response?.error ? "alert" : ""}`}>{badge}</span>}
              </button>
            ))}
            {results.length > 1 && panel === "results" && (
              <div className="result-picker">
                {results.map((result, index) => (
                  <button key={index} className={index === resultIndex ? "active" : ""} onClick={() => setResultIndex(index)}>{index + 1} {result.command}</button>
                ))}
              </div>
            )}
          </nav>
          <div className="output-body">
            {panel === "results" && (current ? <ResultTable result={current} /> : <div className="panel-message">{response?.error ? "The statement failed, see Messages." : "Write SQL and press ⌘ + Enter. Select part of the text to run only the selection."}</div>)}
            {panel === "plan" && <PlanView plan={response?.plan} analyzed={response?.analyzed} planError={response?.planError} />}
            {panel === "hints" && <HintsView hints={response?.hints} busy={Boolean(running)} onApply={applyFix} onInsert={insertFix} />}
            {panel === "messages" && (
              <div className="messages">
                {response?.error && (
                  <div className="error-box">
                    <strong>{response.error.code ? `ERROR ${response.error.code}` : "ERROR"}</strong>
                    <p>{response.error.message}</p>
                    {response.error.detail && <p>Detail: {response.error.detail}</p>}
                    {response.error.hint && <p>Hint: {response.error.hint}</p>}
                  </div>
                )}
                {response?.notices?.map((notice, index) => <div key={index} className="notice">{notice}</div>)}
                {!response?.error && !response?.notices?.length && <div className="panel-message">No messages.</div>}
              </div>
            )}
          </div>
        </div>
      </section>
    </div>
  )
}
