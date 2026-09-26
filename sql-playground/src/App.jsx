import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { api } from "./api.js"
import Dictionary from "./components/Dictionary.jsx"
import ErDiagram from "./components/ErDiagram.jsx"
import Playground from "./components/Playground.jsx"
import Problems, { joinNames } from "./components/Problems.jsx"
import SearchModal from "./components/SearchModal.jsx"
import ShortcutsModal from "./components/ShortcutsModal.jsx"
import { setCompletionCatalog } from "./sqlCompletion.js"

const tabs = [
  ["playground", "Playground"],
  ["problems", "Problems"],
  ["dictionary", "Dictionary"],
  ["er", "ER diagram"]
]

const starter = `SELECT c.country,
       count(DISTINCT o.id) AS orders,
       sum(oi.quantity * oi.unit_price) AS revenue
FROM shop.orders o
JOIN shop.customers c ON c.id = o.customer_id
JOIN shop.order_items oi ON oi.order_id = o.id
WHERE o.created_at >= timestamptz '2025-10-01'
GROUP BY c.country
ORDER BY revenue DESC;`

function stored(key, fallback) {
  try {
    const value = localStorage.getItem(key)
    return value === null ? fallback : JSON.parse(value)
  } catch {
    return fallback
  }
}

function store(key, value) {
  try {
    localStorage.setItem(key, JSON.stringify(value))
  } catch {
    return
  }
}

function Boot({ status }) {
  const percent = status?.total ? Math.round((status.step / status.total) * 100) : 0
  return (
    <div className="boot">
      <div className="boot-card">
        <img src="/logo.svg" alt="" />
        <h1>SQL Playground</h1>
        <p>{status?.label ?? "Connecting to the backend"}</p>
        {status?.phase === "seeding" && (
          <>
            <div className="progress"><span style={{ width: `${percent}%` }} /></div>
            <small>Step {status.step} of {status.total}. The first start builds 5M order lines, later starts reuse the data in tmp/pgdata.</small>
          </>
        )}
        {status?.phase === "error" && <pre>{status.error}</pre>}
      </div>
    </div>
  )
}

export default function App() {
  const [tab, setTab] = useState(() => stored("tab", "playground"))
  const [status, setStatus] = useState(null)
  const [catalog, setCatalog] = useState({ schemas: [] })
  const [problems, setProblems] = useState([])
  const [sql, setSql] = useState(() => stored("sql", starter))
  const [analyze, setAnalyze] = useState(() => stored("analyze", false))
  const [runToken, setRunToken] = useState(0)
  const [problemId, setProblemId] = useState(() => stored("problem", null))
  const [schemaName, setSchemaName] = useState("shop")
  const [tableName, setTableName] = useState(null)
  const [modal, setModal] = useState(null)
  const [fullscreen, setFullscreen] = useState(false)
  const editorRef = useRef(null)
  const ready = status?.phase === "ready"

  useEffect(() => store("tab", tab), [tab])
  useEffect(() => store("sql", sql), [sql])
  useEffect(() => store("analyze", analyze), [analyze])
  useEffect(() => store("problem", problemId), [problemId])

  useEffect(() => {
    let timer
    const poll = async () => {
      try {
        const next = await api.status()
        setStatus(next)
        if (next.phase === "ready") return
      } catch {
        setStatus(current => current ?? { phase: "connecting", label: "Waiting for the backend" })
      }
      timer = setTimeout(poll, 1000)
    }
    poll()
    return () => clearTimeout(timer)
  }, [])

  const loadCatalog = useCallback(() => {
    api.catalog().then(next => {
      setCatalog(next)
      setCompletionCatalog(next)
    }).catch(() => {})
  }, [])

  useEffect(() => {
    if (!ready) return
    loadCatalog()
    api.problems().then(setProblems).catch(() => {})
  }, [ready])

  const openSql = useCallback(text => {
    setSql(text)
    setTab("playground")
    setRunToken(token => token + 1)
  }, [])

  const openTable = useCallback((schema, table) => {
    setSchemaName(schema)
    setTableName(table)
    setTab("dictionary")
  }, [])

  useEffect(() => {
    const onKey = event => {
      if (!event.metaKey || event.ctrlKey || event.altKey) return
      const key = event.key.toLowerCase()
      const digit = /^Digit([1-9])$/.exec(event.code)?.[1]
      let handled = true
      if (digit && !event.shiftKey && tabs[Number(digit) - 1]) setTab(tabs[Number(digit) - 1][0])
      else if (key === "k" && !event.shiftKey) setModal(current => current === "search" ? null : "search")
      else if ((key === "/" || event.code === "Slash") && !event.shiftKey) setModal(current => current === "shortcuts" ? null : "shortcuts")
      else if (key === "e" && !event.shiftKey) setAnalyze(current => !current)
      else if (key === "." && !event.shiftKey) api.cancel().catch(() => {})
      else if (key === "enter" && !event.shiftKey && tab === "playground" && !editorRef.current?.hasTextFocus()) setRunToken(token => token + 1)
      else handled = false
      if (handled) {
        event.preventDefault()
        event.stopPropagation()
      }
    }
    window.addEventListener("keydown", onKey, true)
    return () => window.removeEventListener("keydown", onKey, true)
  }, [tab])

  useEffect(() => window.sqlPlayground?.onFullscreen?.(setFullscreen), [])

  const searchItems = useMemo(() => [
    ...tabs.map(([id, title], index) => ({ id: `tab-${id}`, group: "Tab", title, detail: `⌘ ${index + 1}`, run: () => setTab(id) })),
    { id: "action-run", group: "Action", title: "Run query", detail: "⌘ ↵", run: () => { setTab("playground"); setRunToken(token => token + 1) } },
    { id: "action-analyze", group: "Action", title: analyze ? "Turn Analyze plan off" : "Turn Analyze plan on", detail: "⌘ E", run: () => setAnalyze(!analyze) },
    { id: "action-shortcuts", group: "Action", title: "Show keyboard shortcuts", detail: "⌘ /", run: () => setModal("shortcuts") },
    ...problems.map(problem => ({ id: `problem-${problem.id}`, group: "Problem", title: problem.title, detail: problem.summary, run: () => { setProblemId(problem.id); setTab("problems") } })),
    ...problems.flatMap(problem => problem.joins.map(exercise => ({ id: `join-${problem.id}-${exercise.type}`, group: joinNames[exercise.type], title: exercise.title, detail: problem.schema, run: () => openSql(exercise.sql) }))),
    ...catalog.schemas.flatMap(schema => schema.tables.map(table => ({ id: `table-${schema.name}-${table.name}`, group: "Table", title: `${schema.name}.${table.name}`, detail: table.comment, run: () => openTable(schema.name, table.name) }))),
    ...catalog.schemas.map(schema => ({ id: `er-${schema.name}`, group: "ER diagram", title: schema.name, detail: schema.comment, run: () => { setSchemaName(schema.name); setTab("er") } }))
  ], [problems, catalog, analyze])

  function toggleMaximize(event) {
    if (event.target.closest("button, input, kbd")) return
    window.sqlPlayground?.toggleMaximize()
  }

  return (
    <div className={`app-shell ${fullscreen ? "fullscreen" : ""} ${window.sqlPlayground ? "desktop" : ""}`}>
      <header className="topbar" onDoubleClick={toggleMaximize}>
        <div className="brand">
          <img src="/logo.svg" alt="" />
          <span>SQL Playground</span>
          <small>PostgreSQL 18</small>
        </div>
        <nav className="tabs">
          {tabs.map(([id, title], index) => (
            <button key={id} className={tab === id ? "active" : ""} onClick={() => setTab(id)}>
              <span>{index + 1}</span>{title}
            </button>
          ))}
        </nav>
        <div className="top-actions">
          <button className="search-trigger" onClick={() => setModal("search")}>Search <kbd>⌘</kbd><kbd>K</kbd></button>
          <button className="search-trigger" onClick={() => setModal("shortcuts")}>Shortcuts <kbd>⌘</kbd><kbd>/</kbd></button>
          <span className={`db-dot ${ready ? "up" : ""}`} title={status?.label}>{ready ? "db ready" : "db starting"}</span>
        </div>
      </header>
      {!ready ? <Boot status={status} /> : (
        <main className="page">
          <div className="tab-panel" hidden={tab !== "playground"}>
            <Playground catalog={catalog} sql={sql} setSql={setSql} analyze={analyze} setAnalyze={setAnalyze} runToken={runToken} editorRef={editorRef} onCatalogChange={loadCatalog} />
          </div>
          {tab === "problems" && <Problems problems={problems} selected={problemId} onSelect={setProblemId} onOpenSql={openSql} onCatalogChange={loadCatalog} />}
          {tab === "dictionary" && <Dictionary catalog={catalog} schemaName={schemaName} setSchemaName={setSchemaName} tableName={tableName} setTableName={setTableName} onPreview={openSql} />}
          {tab === "er" && <ErDiagram catalog={catalog} schemaName={schemaName} setSchemaName={setSchemaName} onOpenTable={openTable} />}
        </main>
      )}
      {modal === "search" && <SearchModal items={searchItems} onClose={() => setModal(null)} />}
      {modal === "shortcuts" && <ShortcutsModal onClose={() => setModal(null)} />}
    </div>
  )
}
