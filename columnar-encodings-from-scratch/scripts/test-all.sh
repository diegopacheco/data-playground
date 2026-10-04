#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman
require curl
port_up "$(service_port ui)" || fail "app is down, run scripts/start-all.sh first"
mkdir -p "$RUN/logs"

log "rust unit tests (cargo test in $RUST_IMAGE)"
status=0
podman run --rm --name r18-cargo-test --memory 1536m -v "$ROOT:/src:ro" -v "$CARGO_VOLUME:/target" -e CARGO_TARGET_DIR=/target -w /src "$RUST_IMAGE" cargo test --release >"$RUN/logs/cargo-test.log" 2>&1 || status=$?
grep -E "^test |test result" "$RUN/logs/cargo-test.log" || true
[ "$status" = "0" ] || fail "cargo test failed, see .run/logs/cargo-test.log"

log "rerunning the benchmark"
curl -sf -X POST -o /dev/null "$(service_url ui)/api/run" || fail "could not start the benchmark"
wait_until 60 results_ready || fail "benchmark did not finish, see: podman logs r18-app"

log "api tests (tests/test_encodings.py inside r18-app)"
status=0
podman exec r18-app python -m unittest -v tests.test_encodings >"$RUN/logs/tests.log" 2>&1 || status=$?
cat "$RUN/logs/tests.log"
[ "$status" = "0" ] || fail "api tests failed, see .run/logs/tests.log"
log "all tests passed"
