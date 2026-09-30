#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman
require curl
port_up "$(service_port ui)" || fail "ui is down, run scripts/start-all.sh first"

disk_json() {
  podman exec "$1" find /data/kafka -type f -printf '%s %P\n' 2>/dev/null | awk -v node="$1" '
    { total += $1; if ($2 ~ /^orders-[0-9]+\//) { topic += $1; if ($2 ~ /\.log$/) segs += 1 } files = files sep "{\"path\":\"" $2 "\",\"size\":" $1 "}"; sep = "," }
    END { printf "{\"container\":\"%s\",\"files_total_bytes\":%d,\"orders_partition_bytes\":%d,\"orders_segment_files\":%d,\"files\":[%s]}", node, total, topic, segs + 0, files }'
}

container_id() {
  podman inspect -f '{{.Id}}' "$1" | cut -c1-12
}

log "step 1/5 recreate topic orders and produce data/orders.jsonl with acks=all"
api POST /api/produce >/dev/null || fail "produce failed, see: podman logs r9-app"

log "step 2/5 measure what the brokers keep on local disk"
detail="{\"nodes\":[$(disk_json r9-controller),$(disk_json r9-broker)]}"
api POST /api/events "{\"step\":\"local-disk\",\"title\":\"local disk of both nodes after the produce\",\"detail\":$detail}" >/dev/null || fail "could not record the local disk event"

log "step 3/5 kill -9 the broker container and create a brand new one with an empty filesystem"
old_id="$(container_id r9-broker)"
t0="$(date +%s)"
podman rm -f -t 0 r9-broker >/dev/null || fail "could not remove r9-broker"
compose up -d r9-broker >/dev/null 2>&1 || fail "could not recreate r9-broker"
wait_until 60 node_ready r9-broker 1 || fail "recreated broker not ready, see: podman logs r9-broker"
wait_until 60 cluster_settled || fail "recreated broker did not register or partitions have no leader"
new_id="$(container_id r9-broker)"
[ "$old_id" != "$new_id" ] || fail "r9-broker was not recreated"
api POST /api/events "{\"step\":\"recreate-broker\",\"title\":\"broker node 1 killed and replaced by a new container\",\"detail\":{\"old_container\":\"$old_id\",\"new_container\":\"$new_id\",\"seconds_to_serve\":$(( $(date +%s) - t0 )),\"new_container_disk\":$(disk_json r9-broker)}}" >/dev/null || fail "could not record the recreate event"

log "step 4/5 restart the controller node (combined controller and broker)"
since="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
t0="$(date +%s)"
podman restart -t 30 r9-controller >/dev/null || fail "could not restart r9-controller"
wait_until 60 node_ready r9-controller 0 "$since" || fail "controller not ready after restart"
wait_until 60 cluster_settled || fail "brokers did not register or partitions have no leader after the controller restart"
api POST /api/events "{\"step\":\"restart-controller\",\"title\":\"controller node 0 restarted, every broker cache is now cold\",\"detail\":{\"container\":\"$(container_id r9-controller)\",\"seconds_to_serve\":$(( $(date +%s) - t0 ))}}" >/dev/null || fail "could not record the restart event"

log "step 5/5 consume every record from offset 0 with a new consumer group and compare with the input file"
result="$(api POST /api/consume)" || fail "consume failed, see: podman logs r9-app"
printf "%s" "$result" | python3 -c "import json,sys;c=json.load(sys.stdin)['consumed'];print(f\"consumed {c['records']} records, missing {c['missing']}, duplicates {c['duplicates']}, matches input {c['matches_input']}\");sys.exit(0 if c['matches_input'] else 1)" || fail "consumed data does not match the input"
