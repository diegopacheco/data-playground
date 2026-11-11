#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

cluster_exists || fail "cluster $CLUSTER missing, run scripts/setup.sh first"

k apply -f "$ROOT/k8s/postgres.yaml" >/dev/null || fail "postgres apply failed"
log "waiting for postgres"
wait_until 60 postgres_ready || fail "postgres not ready"

log "applying schema and seeding source partitions"
psql_in_cluster < "$ROOT/sql/schema.sql" || fail "schema failed"
psql_in_cluster < "$ROOT/sql/seed.sql" || fail "seed failed"
log "$(psql_in_cluster -At -c "select count(*) || ' events in ' || (select count(*) from pg_inherits where inhparent = 'events'::regclass) || ' partitions' from events")"

for name in $(service_names); do
  port="$(service_port "$name")"
  if port_up "$port"; then
    log "$name already forwarded on $port"
    continue
  fi
  target="$(service_target "$name")"
  nohup kubectl --context "$CTX" port-forward ${target% *} "$port:${target##* }" > "$RUN/logs/$name.log" 2>&1 &
  echo "$!" > "$RUN/$name.pid"
  wait_until 60 port_up "$port" || fail "port-forward for $name did not open $port, see $RUN/logs/$name.log"
done

for name in $(service_names); do
  log "$name: $(service_url "$name")"
done
