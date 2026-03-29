#!/usr/bin/env bash
set -euo pipefail

ROOT="/home/ankit/Documents/personal-finance-app/mobile/android"
export ANDROID_HOME="${ANDROID_HOME:-/home/ankit/android-sdk}"
export ANDROID_SDK_ROOT="${ANDROID_SDK_ROOT:-$ANDROID_HOME}"

cd "$ROOT"
./gradlew installDebug
