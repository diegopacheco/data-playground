import { formatCount, numericTypes, typeNames } from "../format.js"

export default function ResultTable({ result }) {
  if (!result) return null
  if (result.fields.length === 0) {
    return <div className="result-empty"><strong>{result.command}</strong> completed, {formatCount(result.rowCount)} rows affected.</div>
  }
  return (
    <div className="result-scroll">
      <table className="result-table">
        <thead>
          <tr>
            <th className="row-number">#</th>
            {result.fields.map((field, index) => (
              <th key={index} className={numericTypes.has(field.typeId) ? "numeric" : ""}>
                <span>{field.name}</span>
                <small>{typeNames[field.typeId] ?? field.typeId}</small>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {result.rows.map((row, rowIndex) => (
            <tr key={rowIndex}>
              <td className="row-number">{rowIndex + 1}</td>
              {row.map((value, index) => (
                <td key={index} className={numericTypes.has(result.fields[index].typeId) ? "numeric" : ""}>
                  {value === null ? <span className="null">NULL</span> : value}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {result.truncated && <div className="truncated">Showing the first {formatCount(result.rows.length)} of {formatCount(result.rowCount)} rows. Every row was produced and timed, only the display is capped.</div>}
    </div>
  )
}
