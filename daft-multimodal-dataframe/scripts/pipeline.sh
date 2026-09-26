#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman-compose
podman image exists "$APP_IMAGE" || fail "image $APP_IMAGE missing, run scripts/setup.sh first"

log "running the daft pipeline: csv + images -> thumbnails, features, embeddings -> parquet"
compose run --rm r5-pipeline 2>/dev/null || fail "pipeline failed, rerun: podman-compose run --rm r5-pipeline"
