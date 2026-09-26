#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_NAME="SQL Playground"
BUNDLE_ID="com.diegopacheco.sqlplayground"
TARGET="/Applications/$APP_NAME.app"
KEEP_SETTINGS="${1:-}"
LSREGISTER="/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister"

osascript -e "tell application id \"$BUNDLE_ID\" to quit" >/dev/null 2>&1 &
QUIT_PID=$!
for _ in 1 2 3 4 5 6 7 8 9 10; do
  kill -0 "$QUIT_PID" 2>/dev/null || break
  sleep 1
done
kill "$QUIT_PID" >/dev/null 2>&1 || true
pkill -f "$APP_NAME.app/Contents/MacOS" >/dev/null 2>&1 || true

remove_bundle() {
  local bundle="$1"
  case "$bundle" in
    */"$APP_NAME.app")
      if [ -d "$bundle" ] && [ -f "$bundle/Contents/Info.plist" ]; then
        [ -x "$LSREGISTER" ] && "$LSREGISTER" -u "$bundle" >/dev/null 2>&1 || true
        rm -rf "$bundle"
      fi
      ;;
  esac
}

remove_bundle "$TARGET"
remove_bundle "$HOME/Applications/$APP_NAME.app"
rm -rf "$ROOT/release"

mdfind "kMDItemCFBundleIdentifier == '$BUNDLE_ID'" 2>/dev/null | while IFS= read -r stray; do
  remove_bundle "$stray"
done

if [ "$KEEP_SETTINGS" != "--keep-settings" ]; then
  rm -rf "$HOME/Library/Application Support/SQL Playground" "$HOME/.sql-playground"
fi

echo "Uninstalled. Database files stay in $ROOT/tmp/pgdata"
