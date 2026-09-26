import { useEffect, useMemo, useRef, useState } from "react"

export default function SearchModal({ items, onClose }) {
  const [query, setQuery] = useState("")
  const [active, setActive] = useState(0)
  const input = useRef(null)
  const list = useRef(null)
  useEffect(() => input.current?.focus(), [])
  const matches = useMemo(() => {
    const words = query.toLowerCase().split(/\s+/).filter(Boolean)
    return items.filter(item => words.every(word => `${item.group} ${item.title} ${item.detail ?? ""}`.toLowerCase().includes(word))).slice(0, 60)
  }, [items, query])
  useEffect(() => setActive(0), [query])
  useEffect(() => {
    list.current?.querySelector(".active")?.scrollIntoView({ block: "nearest" })
  }, [active])
  function choose(item) {
    onClose()
    item.run()
  }
  function onKeyDown(event) {
    if (event.key === "ArrowDown") {
      event.preventDefault()
      setActive(Math.min(matches.length - 1, active + 1))
    } else if (event.key === "ArrowUp") {
      event.preventDefault()
      setActive(Math.max(0, active - 1))
    } else if (event.key === "Enter" && matches[active]) {
      event.preventDefault()
      choose(matches[active])
    } else if (event.key === "Escape") {
      event.preventDefault()
      if (query) setQuery("")
      else onClose()
    }
  }
  return (
    <div className="modal-backdrop" onMouseDown={onClose}>
      <div className="modal search-modal" onMouseDown={event => event.stopPropagation()}>
        <div className="search-field">
          <svg viewBox="0 0 20 20" aria-hidden="true"><circle cx="9" cy="9" r="6" /><path d="M13.5 13.5 18 18" /></svg>
          <input ref={input} value={query} onChange={event => setQuery(event.target.value)} onKeyDown={onKeyDown} placeholder="Search tabs, problems, tables, joins and actions" />
          <kbd>esc</kbd>
        </div>
        <ul className="search-results" ref={list}>
          {matches.map((item, index) => (
            <li key={item.id}>
              <button className={index === active ? "active" : ""} onMouseEnter={() => setActive(index)} onClick={() => choose(item)}>
                <span className="search-group">{item.group}</span>
                <span className="search-title">{item.title}</span>
                {item.detail && <span className="search-detail">{item.detail}</span>}
              </button>
            </li>
          ))}
          {matches.length === 0 && <li className="search-empty">Nothing matches "{query}".</li>}
        </ul>
        <footer><span><kbd>↑</kbd><kbd>↓</kbd> move</span><span><kbd>↵</kbd> go</span><span><kbd>esc</kbd> close</span></footer>
      </div>
    </div>
  )
}
