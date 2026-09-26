import { useState } from "react"
import { formatCount, formatDuration } from "../format.js"

function inclusiveTime(node) {
  return (node["Actual Total Time"] ?? 0) * (node["Actual Loops"] ?? 1)
}

function exclusiveTime(node) {
  const children = (node.Plans ?? []).filter(child => child["Parent Relationship"] !== "InitPlan" && child["Parent Relationship"] !== "SubPlan")
  return Math.max(0, inclusiveTime(node) - children.reduce((sum, child) => sum + inclusiveTime(child), 0))
}

function exclusiveCost(node) {
  return Math.max(0, node["Total Cost"] - (node.Plans ?? []).reduce((sum, child) => sum + child["Total Cost"], 0))
}

function label(node) {
  const parts = [node["Node Type"]]
  if (node["Join Type"] && node["Node Type"].includes("Join") || node["Node Type"] === "Nested Loop") parts.push(`(${node["Join Type"]})`)
  if (node["Relation Name"]) parts.push(`on ${node.Schema ? `${node.Schema}.` : ""}${node["Relation Name"]}${node.Alias && node.Alias !== node["Relation Name"] ? ` ${node.Alias}` : ""}`)
  if (node["Index Name"]) parts.push(`using ${node["Index Name"]}`)
  if (node["CTE Name"]) parts.push(`CTE ${node["CTE Name"]}`)
  return parts.join(" ")
}

const detailKeys = ["Filter", "Index Cond", "Recheck Cond", "Hash Cond", "Merge Cond", "Join Filter", "Sort Key", "Group Key", "Sort Method", "Sort Space Used", "Sort Space Type", "Rows Removed by Filter", "Rows Removed by Index Recheck", "Heap Fetches", "Hash Buckets", "Hash Batches", "Peak Memory Usage", "Workers Planned", "Workers Launched", "Shared Hit Blocks", "Shared Read Blocks", "Temp Read Blocks", "Temp Written Blocks", "Strategy", "Output"]

function tone(share) {
  if (share > 0.5) return "hot"
  if (share > 0.2) return "warm"
  return "cool"
}

function PlanNode({ node, total, analyzed, depth }) {
  const [open, setOpen] = useState(false)
  const own = analyzed ? exclusiveTime(node) : exclusiveCost(node)
  const share = total > 0 ? own / total : 0
  const actualRows = analyzed ? node["Actual Rows"] * (node["Actual Loops"] ?? 1) : null
  const off = analyzed && node["Actual Loops"] > 0 ? Math.max(actualRows, 1) / Math.max(node["Plan Rows"] * (node["Actual Loops"] ?? 1), 1) : 1
  const details = detailKeys.filter(key => node[key] !== undefined && node[key] !== null)
  return (
    <li className="plan-node">
      <button className={`plan-row ${open ? "open" : ""}`} style={{ "--depth": depth }} onClick={() => setOpen(!open)}>
        <span className="plan-bar"><span className={tone(share)} style={{ width: `${Math.max(2, share * 100)}%` }} /></span>
        <span className="plan-label">{node["Parent Relationship"] && depth > 0 && <em>{node["Parent Relationship"]}</em>}{label(node)}</span>
        <span className="plan-metric">{analyzed ? formatDuration(own) : `cost ${formatCount(own)}`}</span>
        <span className="plan-metric">{(share * 100).toFixed(1)}%</span>
        <span className="plan-metric">est {formatCount(node["Plan Rows"])}</span>
        <span className={`plan-metric ${off > 10 || off < 0.1 ? "misestimate" : ""}`}>{analyzed ? `act ${formatCount(actualRows)}` : ""}</span>
        <span className="plan-metric">{analyzed ? `x${node["Actual Loops"]}` : ""}</span>
      </button>
      {open && details.length > 0 && (
        <dl className="plan-details" style={{ "--depth": depth }}>
          {details.map(key => (
            <div key={key}><dt>{key}</dt><dd>{Array.isArray(node[key]) ? node[key].join(", ") : String(node[key])}</dd></div>
          ))}
        </dl>
      )}
      {node.Plans?.length > 0 && (
        <ul>{node.Plans.map((child, index) => <PlanNode key={index} node={child} total={total} analyzed={analyzed} depth={depth + 1} />)}</ul>
      )}
    </li>
  )
}

function buffers(plan) {
  const root = plan.Plan
  return { hit: root["Shared Hit Blocks"], read: root["Shared Read Blocks"] }
}

export default function PlanView({ plan, analyzed, planError }) {
  const [raw, setRaw] = useState(false)
  if (planError) return <div className="panel-message">No plan: {planError}</div>
  if (!plan) return <div className="panel-message">Run a single SELECT, WITH, INSERT, UPDATE, DELETE or MERGE to see its plan.</div>
  const root = plan.Plan
  const total = analyzed ? inclusiveTime(root) : root["Total Cost"]
  const io = buffers(plan)
  return (
    <div className="plan-view">
      <div className="plan-summary">
        <div><small>Mode</small><strong>{analyzed ? "EXPLAIN ANALYZE" : "EXPLAIN (estimates)"}</strong></div>
        <div><small>Total cost</small><strong>{formatCount(root["Total Cost"])}</strong></div>
        <div><small>Estimated rows</small><strong>{formatCount(root["Plan Rows"])}</strong></div>
        {plan["Planning Time"] !== undefined && <div><small>Planning</small><strong>{formatDuration(plan["Planning Time"])}</strong></div>}
        {plan["Execution Time"] !== undefined && <div><small>Execution</small><strong>{formatDuration(plan["Execution Time"])}</strong></div>}
        {io.hit !== undefined && <div><small>Buffers hit / read</small><strong>{formatCount(io.hit)} / {formatCount(io.read)}</strong></div>}
        <button className="ghost-button" onClick={() => setRaw(!raw)}>{raw ? "Tree" : "JSON"}</button>
      </div>
      {!analyzed && <div className="plan-note">Bars show each node's own share of the estimated cost. Turn on Analyze to measure real time per node.</div>}
      {raw ? <pre className="plan-json">{JSON.stringify(plan, null, 2)}</pre> : <ul className="plan-tree"><PlanNode node={root} total={total} analyzed={analyzed} depth={0} /></ul>}
    </div>
  )
}
