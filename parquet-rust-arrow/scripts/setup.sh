#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

log "setup started"

require cargo
if command -v rustup >/dev/null 2>&1; then
  rustup toolchain install "$(awk -F'"' '/channel/{print $2}' "$ROOT/rust-toolchain.toml")" --profile minimal >/dev/null || fail "rustup toolchain install failed"
fi
cargo fetch || fail "cargo fetch failed"
build_app

log "setup done"
