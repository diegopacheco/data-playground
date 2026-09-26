import { useEffect, useMemo, useRef, useState } from "react"

const icons = {
  run: <path d="M6 4.5v11l9-5.5z" />,
  nav: <><rect x="3" y="4" width="14" height="12" rx="2" /><path d="M3 8h14M8 8v8" /></>,
  window: <><rect x="3" y="3.5" width="14" height="13" rx="2" /><path d="M3 7h14M6.5 5.2h.01M9 5.2h.01" /></>,
  edit: <><path d="M4 16l1-4 8-8 3 3-8 8z" /><path d="M11.5 5.5l3 3" /></>,
  search: <><circle cx="9" cy="9" r="5.5" /><path d="M13 13l4 4" /></>
}

export const shortcutGroups = [
  { id: "run", title: "Running queries", color: "#1f6fb2", icon: "run", items: [
    [["⌘", "↵"], "Run the editor, or only the selected text"],
    [["⌘", "."], "Cancel the running query"],
    [["⌘", "E"], "Toggle EXPLAIN ANALYZE for the plan"]
  ] },
  { id: "nav", title: "Navigation", color: "#2f8a5b", icon: "nav", items: [
    [["⌘", "1"], "Playground"],
    [["⌘", "2"], "Problems"],
    [["⌘", "3"], "Dictionary"],
    [["⌘", "4"], "ER diagram"],
    [["⌘", "K"], "Search anything"],
    [["⌘", "/"], "This shortcut guide"]
  ] },
  { id: "edit", title: "Editor", color: "#b0662a", icon: "edit", items: [
    [["⌃", "Space"], "Open autocomplete"],
    [["⌘", "C"], "Copy"],
    [["⌘", "X"], "Cut"],
    [["⌘", "V"], "Paste"],
    [["⌘", "Z"], "Undo"],
    [["⌘", "F"], "Find in editor"]
  ] },
  { id: "window", title: "Window", color: "#7a4bb0", icon: "window", items: [
    [["⌘", "+"], "Zoom in"],
    [["⌘", "-"], "Zoom out"],
    [["⌘", "⇧", "0"], "Reset zoom"],
    [["⌘", "P"], "Capture a region of the screen"],
    [["⌘", "⇧", "↵"], "Toggle full screen"],
    [["Double click", "top bar"], "Maximize or restore the window"]
  ] },
  { id: "search", title: "Search and modals", color: "#b23a48", icon: "search", items: [
    [["↑", "↓"], "Move through results"],
    [["↵"], "Open the selected result"],
    [["esc"], "Clear the search, then close"]
  ] }
]

export default function ShortcutsModal({ onClose }) {
  const [query, setQuery] = useState("")
  const input = useRef(null)
  useEffect(() => input.current?.focus(), [])
  const groups = useMemo(() => {
    const needle = query.trim().toLowerCase()
    if (!needle) return shortcutGroups
    return shortcutGroups
      .map(group => group.title.toLowerCase().includes(needle) ? group : { ...group, items: group.items.filter(([keys, text]) => `${keys.join(" ")} ${text}`.toLowerCase().includes(needle)) })
      .filter(group => group.items.length > 0)
  }, [query])
  const count = groups.reduce((sum, group) => sum + group.items.length, 0)
  function onKeyDown(event) {
    if (event.key !== "Escape") return
    event.preventDefault()
    if (query) setQuery("")
    else onClose()
  }
  return (
    <div className="modal-backdrop" onMouseDown={onClose}>
      <div className="modal shortcuts-modal" onMouseDown={event => event.stopPropagation()}>
        <div className="search-field">
          <svg viewBox="0 0 20 20" aria-hidden="true"><circle cx="9" cy="9" r="6" /><path d="M13.5 13.5 18 18" /></svg>
          <input ref={input} value={query} onChange={event => setQuery(event.target.value)} onKeyDown={onKeyDown} placeholder="Filter shortcuts" />
          <span className="shortcut-count">{count} shortcuts</span>
        </div>
        <div className="shortcut-columns">
          {groups.map(group => (
            <section key={group.id} className="shortcut-group" style={{ "--group": group.color }}>
              <h3><svg viewBox="0 0 20 20" aria-hidden="true">{icons[group.icon]}</svg>{group.title}</h3>
              {group.items.map(([keys, text]) => (
                <div key={text} className="shortcut-row">
                  <span className="shortcut-keys">{keys.map(key => <kbd key={key}>{key}</kbd>)}</span>
                  <span>{text}</span>
                </div>
              ))}
            </section>
          ))}
          {groups.length === 0 && <p className="search-empty">No shortcut matches "{query}".</p>}
        </div>
      </div>
    </div>
  )
}
