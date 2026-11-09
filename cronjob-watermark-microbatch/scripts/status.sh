#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

if cluster_exists; then
  pg="$(k get statefulset postgres -o jsonpath='{.status.readyReplicas}' 2>/dev/null || true)"
  gen="$(k get deployment generator -o jsonpath='{.status.readyReplicas}' 2>/dev/null || true)"
  log "cluster $CLUSTER UP, postgres ready=${pg:-0}, generator ready=${gen:-0}"
  for cj in java-loader python-loader; do
    info="$(k get cronjob "$cj" -o jsonpath='suspend={.spec.suspend} last={.status.lastScheduleTime}' 2>/dev/null || true)"
    log "cronjob $cj ${info:-ABSENT}"
  done
  if [ "${pg:-0}" = "1" ]; then
    psql_exec -At -F ' ' -c "SELECT 'watermark', w.job, w.last_updated_at, w.last_id, 'runs=' || count(r.id) FROM watermarks w LEFT JOIN batch_runs r ON r.job = w.job GROUP BY w.job, w.last_updated_at, w.last_id ORDER BY w.job" || fail "watermark query failed"
  fi
else
  log "cluster $CLUSTER DOWN"
fi

for name in $(service_names); do
  port="$(service_port "$name")"
  if port_up "$port"; then
    log "$name $port UP pid=$(port_pid "$port") $(service_url "$name")"
  else
    log "$name $port DOWN"
  fi
done
