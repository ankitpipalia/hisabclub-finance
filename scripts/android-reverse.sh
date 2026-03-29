#!/usr/bin/env bash
set -euo pipefail

DEVICE_ID="${1:-}"
ADB=(adb)
if [[ -n "$DEVICE_ID" ]]; then
  ADB+=( -s "$DEVICE_ID" )
fi

"${ADB[@]}" reverse tcp:8356 tcp:8356
"${ADB[@]}" reverse tcp:8081 tcp:8081
"${ADB[@]}" reverse --remove tcp:8000 >/dev/null 2>&1 || true
"${ADB[@]}" reverse --remove tcp:8611 >/dev/null 2>&1 || true
"${ADB[@]}" reverse --list
