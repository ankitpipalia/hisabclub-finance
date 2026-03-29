#!/usr/bin/env bash
set -euo pipefail

ROOT="/home/ankit/Documents/personal-finance-app"
DEVICE_ID="${1:-}"
export ANDROID_HOME="${ANDROID_HOME:-/home/ankit/android-sdk}"
export ANDROID_SDK_ROOT="${ANDROID_SDK_ROOT:-$ANDROID_HOME}"
export NODE_ENV="${NODE_ENV:-development}"

if [[ -n "$DEVICE_ID" ]]; then
  "$ROOT/scripts/android-reverse.sh" "$DEVICE_ID"
else
  "$ROOT/scripts/android-reverse.sh"
fi

cd "$ROOT/mobile"
exec npx expo start --dev-client --host localhost --port 8081
