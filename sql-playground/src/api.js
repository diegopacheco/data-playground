async function call(path, body) {
  const response = await fetch(path, {
    method: body === undefined ? "GET" : "POST",
    headers: { "content-type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body)
  })
  const data = await response.json()
  if (!response.ok) throw new Error(data.error ?? `request failed with ${response.status}`)
  return data
}

export const api = {
  status: () => call("/api/status"),
  catalog: () => call("/api/catalog"),
  problems: () => call("/api/problems"),
  query: (sql, analyze) => call("/api/query", { sql, analyze }),
  cancel: () => call("/api/cancel", {}),
  reset: id => call(`/api/problems/${id}/reset`, {}),
  race: (id, mode) => call(`/api/problems/${id}/race`, { mode })
}
