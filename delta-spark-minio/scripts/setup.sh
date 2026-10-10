#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

log "setup started"

require podman
require podman-compose
podman info >/dev/null 2>&1 || fail "podman is not reachable, start the podman machine"
podman-compose pull

if [ ! -d "$HOME/.sdkman/candidates/java/$JAVA_SDK" ] && [ -s "$HOME/.sdkman/bin/sdkman-init.sh" ]; then
  set +u
  source "$HOME/.sdkman/bin/sdkman-init.sh"
  sdk install java "$JAVA_SDK" </dev/null
  set -u
  export JAVA_HOME="$HOME/.sdkman/candidates/java/$JAVA_SDK"
  export PATH="$JAVA_HOME/bin:$PATH"
fi

require java
require sbt
sbt -batch compile

log "setup done"
