#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_NAME="SQL Playground"
BUNDLE_ID="com.diegopacheco.sqlplayground"
TARGET="/Applications/$APP_NAME.app"
CONFIG="$HOME/.sql-playground"
LSREGISTER="/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister"

cd "$ROOT"
for tool in node npm podman podman-compose; do
  command -v "$tool" >/dev/null 2>&1 || { echo "$tool is required" >&2; exit 1; }
done

echo "Removing any installed copy"
"$ROOT/uninstall.sh" --keep-settings

echo "Preparing dependencies"
"$ROOT/scripts/setup.sh"

echo "Recording the project folder and PATH for the app"
mkdir -p "$CONFIG"
printf '%s\n' "$ROOT" >"$CONFIG/root"
printf '%s\n' "$PATH" >"$CONFIG/path"

echo "Packaging the app"
rm -rf "$ROOT/release"
npx electron-builder --mac dir >"$ROOT/.run/logs/package.log" 2>&1 || { echo "packaging failed, see .run/logs/package.log" >&2; exit 1; }

BUILT="$(find "$ROOT/release" -maxdepth 2 -name "$APP_NAME.app" -type d | head -1)"
[ -n "$BUILT" ] || { echo "electron-builder produced no app bundle" >&2; exit 1; }

echo "Installing to $TARGET"
ditto "$BUILT" "$TARGET"
[ -x "$LSREGISTER" ] && "$LSREGISTER" -u "$BUILT" >/dev/null 2>&1 || true
rm -rf "$ROOT/release"

codesign --force --deep --sign - --identifier "$BUNDLE_ID" "$TARGET" >/dev/null 2>&1 || true
xattr -dr com.apple.quarantine "$TARGET" >/dev/null 2>&1 || true
[ -x "$LSREGISTER" ] && "$LSREGISTER" -f "$TARGET" >/dev/null 2>&1 || true

COPIES="$(find /Applications "$HOME/Applications" -maxdepth 1 -name "$APP_NAME.app" -type d 2>/dev/null | wc -l | tr -d ' ')"
if [ "$COPIES" != "1" ]; then
  echo "Expected exactly one installed copy of $APP_NAME, found $COPIES" >&2
  exit 1
fi

echo "Installed one copy at $TARGET"
echo "Open it from Applications or run: open -a \"$APP_NAME\""
