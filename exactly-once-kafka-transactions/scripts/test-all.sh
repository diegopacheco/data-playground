#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require curl
require jq
port_up "$(service_port ui)" || fail "ui is down, run scripts/start-all.sh first"

PAYMENTS="$ROOT/data/payments.csv"
API="$(service_url ui)/api"

settled() {
  awk -F, -v batch="$BATCH" -v again="$1" 'BEGIN { n = split(again, at, " ") }
    NR>1 {
      copies = 1
      for (i = 1; i <= n; i++) if ($1 > int(at[i] / batch) * batch && $1 <= at[i]) copies++
      for (c = 0; c < copies; c++) printf "%d,%s,%d,%d\n", $1, $2, $3, int($3 * 3 / 100)
    }' "$PAYMENTS" | sort
}

topic() {
  dump_topic "$1-out" "$2" | sort
}

summary() {
  printf "%s\n" "$1" | awk -F, 'NF { n++; if (seen[$1]++) d++ } END { printf "records=%d distinct=%d duplicates=%d", n, n - d, d }'
}

api_summary() {
  printf "%s" "$report" | jq -r --arg s "$1" --arg v "$2" '.scenarios[] | select(.name == $s) | .[$v] | "records=\(.records) distinct=\(.distinct) duplicates=\(.duplicates)"'
}

check() {
  if [ "$2" = "$3" ]; then
    log "PASS $1"
  else
    printf "FAIL %s\nexpected:\n%s\nactual:\n%s\n" "$1" "$(printf "%s\n" "$2" | head -20)" "$(printf "%s\n" "$3" | head -20)" >&2
    exit 1
  fi
}

report="$(curl -sf "$API/report")" || fail "GET /api/report failed"
input="$(($(wc -l <"$PAYMENTS") - 1))"
once="$(settled "")"
killed="$(settled "$KILL_OFFSETS")"
fenced="$(settled "$FENCE_OFFSET")"

tx_committed="$(topic transactional read_committed)"
tx_uncommitted="$(topic transactional read_uncommitted)"
check "transactional read_committed equals awk settlement of payments.csv, exactly once" "$once" "$tx_committed"
check "transactional read_committed has $input records, 0 duplicates" "records=$input distinct=$input duplicates=0" "$(summary "$tx_committed")"
check "transactional read_uncommitted also holds the records of both killed transactions" "$killed" "$tx_uncommitted"
check "transactional api numbers equal the console consumer read_committed" "$(summary "$tx_committed")" "$(api_summary transactional committed)"
check "transactional api numbers equal the console consumer read_uncommitted" "$(summary "$tx_uncommitted")" "$(api_summary transactional uncommitted)"

alo_committed="$(topic at-least-once read_committed)"
check "at-least-once read_committed shows the re-sent records as duplicates" "$killed" "$alo_committed"
[ "$alo_committed" != "$once" ] || fail "at-least-once output has no duplicates, the contrast is gone"
log "PASS at-least-once output differs from exactly once"
check "at-least-once api numbers equal the console consumer read_committed" "$(summary "$alo_committed")" "$(api_summary at-least-once committed)"

fence_committed="$(topic fencing read_committed)"
fence_uncommitted="$(topic fencing read_uncommitted)"
check "fencing zombie was rejected with ProducerFencedException" "ProducerFencedException" "$(cat "$RUN/fencing.fenced" 2>/dev/null || true)"
check "fencing read_committed equals awk settlement, the zombie added nothing" "$once" "$fence_committed"
check "fencing read_uncommitted holds only the zombie records sent before it was fenced" "$fenced" "$fence_uncommitted"
check "fencing api reports the exception" "ProducerFencedException" "$(printf "%s" "$report" | jq -r '.scenarios[] | select(.name == "fencing") | .fenced')"

offsets="$(kafka_tool kafka-consumer-groups.sh --describe --all-groups 2>/dev/null | awk '$2 ~ /-in$/ {print $1, $4}' | sort)"
check "every consumer group committed offset $input, the input is drained" "at-least-once-group $input
fencing-group $input
transactional-group $input" "$offsets"

log "input payments:                    $input"
log "transactional  read_committed:     $(summary "$tx_committed")"
log "transactional  read_uncommitted:   $(summary "$tx_uncommitted")"
log "at-least-once  read_committed:     $(summary "$alo_committed")"
log "fencing        read_committed:     $(summary "$fence_committed")"
log "fencing        read_uncommitted:   $(summary "$fence_uncommitted")"
log "all tests passed"
