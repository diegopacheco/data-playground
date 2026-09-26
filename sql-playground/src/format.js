export function formatDuration(ms) {
  if (!Number.isFinite(ms) || ms < 0) return "-"
  if (ms < 1) return `${ms.toFixed(3)} ms`
  if (ms < 1000) return `${ms.toFixed(ms < 10 ? 2 : 1)} ms`
  const seconds = ms / 1000
  if (seconds < 59.995) return `${seconds.toFixed(2)} s`
  const whole = Math.round(seconds)
  const minutes = Math.floor(whole / 60)
  if (minutes < 60) return `${minutes} m ${String(whole % 60).padStart(2, "0")} s`
  const hours = Math.floor(minutes / 60)
  return `${hours} h ${String(minutes % 60).padStart(2, "0")} m`
}

export function formatCount(value) {
  return Math.round(Number(value) || 0).toLocaleString("en-US")
}

export function formatBytes(bytes) {
  const units = ["B", "kB", "MB", "GB", "TB"]
  let value = Number(bytes) || 0
  let unit = 0
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024
    unit++
  }
  return `${value.toFixed(unit === 0 ? 0 : 1)} ${units[unit]}`
}

export function compactCount(value) {
  const number = Number(value) || 0
  if (number >= 1e6) return `${(number / 1e6).toFixed(number >= 1e7 ? 0 : 1)}M`
  if (number >= 1e3) return `${(number / 1e3).toFixed(number >= 1e4 ? 0 : 1)}k`
  return String(Math.round(number))
}

export const typeNames = {
  16: "bool", 18: "char", 19: "name", 20: "int8", 21: "int2", 23: "int4", 25: "text", 26: "oid", 114: "json",
  700: "float4", 701: "float8", 1042: "bpchar", 1043: "varchar", 1082: "date", 1083: "time", 1114: "timestamp",
  1184: "timestamptz", 1186: "interval", 1700: "numeric", 2950: "uuid", 3802: "jsonb", 3904: "int4range",
  3910: "tstzrange", 3912: "daterange", 1009: "text[]", 1007: "int4[]", 1016: "int8[]", 1003: "name[]"
}

export const numericTypes = new Set([20, 21, 23, 26, 700, 701, 1700])
