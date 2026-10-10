#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

log "tests started"

require cargo
cargo test || fail "cargo tests failed"

[ -x "$BIN" ] || build_app

awk_aggregates() {
  awk -F, -v from="$1" 'NR>1 && $7>=from {o[$4]++; q[$4]+=$5; r[$4]+=$5*$6} END {for (c in o) printf "%s,%d,%d,%.2f\n", c, o[c], q[c], r[c]}' "$ROOT/data/orders.csv" | sort
}

for day in "" 2026-01-08 2026-01-12 2026-01-16; do
  expected="$(awk_aggregates "$day")"
  actual="$("$BIN" aggregates $day 2>/dev/null | sort)"
  if [ "$expected" != "$actual" ]; then
    printf "expected:\n%s\nactual:\n%s\n" "$expected" "$actual" >&2
    fail "aggregates differ from awk for from=${day:-all}"
  fi
  log "aggregates match awk for from=${day:-all}"
  printf "%s\n" "$actual"
done

port="$(service_port ui)"
if port_up "$port"; then
  body="$(curl -fsS "$(service_url ui)/api/aggregates?from=2026-01-16")" || fail "api call failed"
  case "$body" in
    *'"row_groups_read":[3],"rows_read":42'*) log "api pruned to row group 3 with 42 rows" ;;
    *) fail "unexpected api response: $body" ;;
  esac
  curl -fsS "$(service_url ui)/api/metadata" | grep -q '"compression":"ZSTD"' || fail "metadata api does not report ZSTD"
  log "metadata api reports ZSTD"
fi

log "tests passed"
