#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

for tool in podman kind kubectl python3 lsof curl; do require "$tool"; done

if [ -s "$ARGO_INSTALL" ]; then
  log "argo $ARGO_VERSION install manifest already downloaded"
else
  curl -sfL -o "$ARGO_INSTALL.tmp" "https://github.com/argoproj/argo-workflows/releases/download/$ARGO_VERSION/install.yaml" || fail "argo install manifest download failed"
  mv "$ARGO_INSTALL.tmp" "$ARGO_INSTALL"
fi

podman build -t "$APP_IMAGE" -f "$ROOT/Containerfile" "$ROOT" || fail "image build failed"
log "setup done"
