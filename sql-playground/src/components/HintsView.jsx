const labels = { critical: "Fix this", warning: "Improve", info: "Worth knowing", good: "Good" }

export default function HintsView({ hints, onApply, onInsert, busy }) {
  if (!hints) return <div className="panel-message">Run a query to get hints.</div>
  if (hints.length === 0) return <div className="panel-message">No hints for this statement.</div>
  return (
    <div className="hints">
      {hints.map((hint, index) => (
        <article key={index} className={`hint hint-${hint.level}`}>
          <header>
            <span className="hint-level">{labels[hint.level]}</span>
            <h3>{hint.title}</h3>
          </header>
          <p>{hint.detail}</p>
          {hint.fix && (
            <div className="hint-fix">
              <code>{hint.fix}</code>
              <button className="ghost-button" disabled={busy} onClick={() => onInsert(hint.fix)}>Insert</button>
              <button className="primary-button small" disabled={busy} onClick={() => onApply(hint.fix)}>Apply and re-run</button>
            </div>
          )}
        </article>
      ))}
    </div>
  )
}
