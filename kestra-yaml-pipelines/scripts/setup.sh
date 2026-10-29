#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

log "setup started"
require podman
require podman-compose
require curl
require python3

podman pull -q docker.io/library/postgres:18.6-alpine >/dev/null
podman pull -q "$KESTRA_IMAGE" >/dev/null

podman volume exists i40-kestra-plugins || podman volume create i40-kestra-plugins >/dev/null
installed="$(podman run --rm -v i40-kestra-plugins:/app/plugins --entrypoint ls "$KESTRA_IMAGE" /app/plugins)"
missing=""
for plugin in $KESTRA_PLUGINS; do
  jar="$(printf "%s" "$plugin" | awk -F: '{gsub(/\./,"_",$1); gsub(/\./,"_",$3); print $1"__"$2"__"$3".jar"}')"
  printf "%s\n" "$installed" | grep -qx "$jar" || missing="$missing $plugin"
done
if [ -n "$missing" ]; then
  log "installing kestra plugins:$missing"
  podman run --rm --user root -v i40-kestra-plugins:/app/plugins "$KESTRA_IMAGE" plugins install $missing >"$LOGS/plugins.log" 2>&1 || fail "plugin install failed, see $LOGS/plugins.log"
fi
log "kestra plugins ready"

podman-compose build >"$LOGS/build.log" 2>&1 || fail "image build failed, see $LOGS/build.log"

if [ ! -f "$ROOT/.gitignore" ] || ! grep -q '^\.run/$' "$ROOT/.gitignore"; then
  printf ".run/\n" >>"$ROOT/.gitignore"
fi

log "setup done"
