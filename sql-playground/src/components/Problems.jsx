import { useEffect, useState } from "react"
import { api } from "../api.js"
import { formatDuration } from "../format.js"
import { colorize } from "./SqlEditor.jsx"

export const joinNames = {
  inner: "INNER JOIN",
  left: "LEFT JOIN",
  right: "RIGHT JOIN",
  full: "FULL OUTER JOIN",
  cross: "CROSS JOIN",
  self: "SELF JOIN",
  semi: "SEMI JOIN (EXISTS)",
  anti: "ANTI JOIN (NOT EXISTS)",
  lateral: "LATERAL JOIN"
}

function Venn({ type }) {
  const fill = {
    inner: { left: false, middle: true, right: false },
    left: { left: true, middle: true, right: false },
    right: { left: false, middle: true, right: true },
    full: { left: true, middle: true, right: true },
    semi: { left: false, middle: true, right: false },
    anti: { left: true, middle: false, right: false }
  }[type]
  if (type === "cross") {
    return (
      <svg viewBox="0 0 64 40" className="venn">
        {[0, 1, 2].map(row => [0, 1, 2, 3].map(col => <rect key={`${row}${col}`} x={10 + col * 12} y={5 + row * 11} width="9" height="8" rx="2" className="on" />))}
      </svg>
    )
  }
  if (type === "self") {
    return (
      <svg viewBox="0 0 64 40" className="venn">
        <circle cx="26" cy="20" r="14" className="on" />
        <path d="M38 12 C 58 2, 60 34, 38 28" className="arrow" />
        <path d="M40 24 l-3 4 l5 1" className="arrow" />
      </svg>
    )
  }
  if (type === "lateral") {
    return (
      <svg viewBox="0 0 64 40" className="venn">
        {[8, 18, 28].map(y => <rect key={y} x="6" y={y - 3} width="16" height="6" rx="2" className="on" />)}
        {[8, 18, 28].map(y => <path key={y} d={`M24 ${y} H40`} className="arrow" />)}
        <rect x="42" y="4" width="16" height="30" rx="4" className="off" />
      </svg>
    )
  }
  return (
    <svg viewBox="0 0 64 40" className="venn">
      <defs>
        <clipPath id={`clip-${type}`}><circle cx="24" cy="20" r="14" /></clipPath>
      </defs>
      <circle cx="24" cy="20" r="14" className={fill.left ? "on" : "off"} />
      <circle cx="40" cy="20" r="14" className={fill.right ? "on" : "off"} />
      <circle cx="40" cy="20" r="14" clipPath={`url(#clip-${type})`} className={fill.middle ? "on strong" : "cut"} />
      <circle cx="24" cy="20" r="14" className="outline" />
      <circle cx="40" cy="20" r="14" className="outline" />
    </svg>
  )
}

function Code({ sql }) {
  const [html, setHtml] = useState("")
  useEffect(() => {
    let alive = true
    colorize(sql).then(value => alive && setHtml(value))
    return () => {
      alive = false
    }
  }, [sql])
  return <pre className="code-block" dangerouslySetInnerHTML={{ __html: html }} />
}

function RaceResult({ result }) {
  if (!result) return null
  if (result.error) return <div className="race-result failed"><strong>Error</strong><p>{result.error}</p></div>
  return (
    <div className={`race-result ${result.ok ? "passed" : "failed"}`}>
      <div className="race-verdict">
        <strong>{result.ok ? "Invariant held" : "Invariant broken"}</strong>
        <span>{result.clients} clients x {result.iterations} runs in {formatDuration(result.elapsedMs)}</span>
      </div>
      <table className="mini-table">
        <thead><tr>{result.check.fields.map(field => <th key={field}>{field}</th>)}</tr></thead>
        <tbody>{result.check.rows.map((row, index) => <tr key={index}>{row.map((value, cell) => <td key={cell}>{value === "t" ? "true" : value === "f" ? "false" : value}</td>)}</tr>)}</tbody>
      </table>
      {result.errors.length > 0 && (
        <ul className="race-errors">{result.errors.map(error => <li key={error.message}><strong>{error.count}x</strong> {error.message}</li>)}</ul>
      )}
    </div>
  )
}

function Race({ problem }) {
  const [results, setResults] = useState({})
  const [busy, setBusy] = useState(null)
  useEffect(() => setResults({}), [problem.id])
  async function start(mode) {
    setBusy(mode)
    try {
      const result = await api.race(problem.id, mode)
      setResults(current => ({ ...current, [mode]: result }))
    } catch (error) {
      setResults(current => ({ ...current, [mode]: { error: error.message } }))
    } finally {
      setBusy(null)
    }
  }
  return (
    <section className="race">
      <div className="section-head">
        <div>
          <p className="eyebrow">Contention race</p>
          <h2>Run it with {problem.race.clients} concurrent sessions</h2>
          <p className="muted">{problem.race.goal}</p>
        </div>
      </div>
      <div className="race-grid">
        {["naive", "safe"].map(mode => (
          <div key={mode} className={`race-card ${mode}`}>
            <header>
              <span className={`mode-tag ${mode}`}>{mode === "naive" ? "Naive" : "Safe"}</span>
              <button className={mode === "naive" ? "danger-button" : "primary-button"} disabled={Boolean(busy)} onClick={() => start(mode)}>
                {busy === mode ? "Racing..." : `Run ${mode} race`}
              </button>
            </header>
            {mode === "safe" && problem.race.safePrepare && <><p className="code-caption">Schema change applied first</p><Code sql={problem.race.safePrepare} /></>}
            <p className="code-caption">Each session runs</p>
            <Code sql={problem.race[mode]} />
            <RaceResult result={results[mode]} />
          </div>
        ))}
      </div>
      <details className="check-sql">
        <summary>Invariant check and reset SQL</summary>
        <p className="code-caption">Before each race</p>
        <Code sql={problem.race.prepare} />
        <p className="code-caption">After each race</p>
        <Code sql={problem.race.check} />
      </details>
    </section>
  )
}

function JoinCard({ exercise, onOpen }) {
  const [open, setOpen] = useState(false)
  return (
    <article className={`join-card join-${exercise.type}`}>
      <header>
        <Venn type={exercise.type} />
        <div>
          <span className="join-type">{joinNames[exercise.type]}</span>
          <h3>{exercise.title}</h3>
        </div>
      </header>
      <p>{exercise.prompt}</p>
      <div className="join-actions">
        <button className="ghost-button" onClick={() => setOpen(!open)}>{open ? "Hide solution" : "Show solution"}</button>
        <button className="primary-button small" onClick={() => onOpen(exercise.sql)}>Run in playground</button>
      </div>
      {open && <Code sql={exercise.sql} />}
    </article>
  )
}

export default function Problems({ problems, selected, onSelect, onOpenSql, onCatalogChange }) {
  const problem = problems.find(candidate => candidate.id === selected) ?? problems[0]
  const [resetting, setResetting] = useState(false)
  if (!problem) return <div className="page-message">Loading problems...</div>
  async function reset() {
    setResetting(true)
    try {
      await api.reset(problem.id)
      onCatalogChange()
    } finally {
      setResetting(false)
    }
  }
  return (
    <div className="problems">
      <aside className="problem-list">
        <div className="side-title">{problems.length} problems</div>
        {problems.map((candidate, index) => (
          <button key={candidate.id} className={candidate.id === problem.id ? "active" : ""} onClick={() => onSelect(candidate.id)}>
            <span className="problem-number">{String(index + 1).padStart(2, "0")}</span>
            <span className="problem-text">
              <strong>{candidate.title}</strong>
              <small>{candidate.schema} schema</small>
            </span>
          </button>
        ))}
      </aside>
      <div className="problem-detail">
        <header className="problem-hero">
          <div>
            <p className="eyebrow">Schema {problem.schema}</p>
            <h1>{problem.title}</h1>
            <p className="lede">{problem.summary}</p>
          </div>
          <button className="ghost-button" disabled={resetting} onClick={reset}>{resetting ? "Resetting..." : "Reset data"}</button>
        </header>
        <section className="background">
          <p className="eyebrow">Background</p>
          {problem.background.map((paragraph, index) => <p key={index}>{paragraph}</p>)}
        </section>
        <Race problem={problem} />
        <section className="joins">
          <div className="section-head">
            <div>
              <p className="eyebrow">Joins on this schema</p>
              <h2>Every join type, one business question each</h2>
            </div>
          </div>
          <div className="join-grid">
            {problem.joins.map(exercise => <JoinCard key={exercise.type} exercise={exercise} onOpen={onOpenSql} />)}
          </div>
        </section>
      </div>
    </div>
  )
}
