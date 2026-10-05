#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
awk -F, 'NR > 1 {
  c = tolower($4); gsub(/^ +| +$/, "", c)
  orders[c] += 1; qty[c] += $5; rev[c] += $5 * $6
}
END {
  for (c in orders) printf "%s,%d,%d,%.2f\n", c, orders[c], qty[c], rev[c]
}' "$ROOT/data/orders.csv" | sort
