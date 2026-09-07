#!/bin/bash
set -euo pipefail
ROOT="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

SDK_ROOT="${ANDROID_SDK_ROOT:-${ANDROID_HOME:-$HOME/Android/Sdk}}"
export ANDROID_SDK_ROOT="$SDK_ROOT"
export ANDROID_HOME="$SDK_ROOT"
export JAVA_HOME="${JAVA_HOME:-/usr/lib/jvm/java-21-openjdk-amd64}"
export PATH="$ROOT/node_modules/.bin:$JAVA_HOME/bin:$SDK_ROOT/platform-tools:$SDK_ROOT/cmdline-tools/latest/bin:$PATH"

if [ ! -d "$SDK_ROOT/platforms/android-35" ]; then
  echo "Android SDK platforms/android-35 missing at $SDK_ROOT" >&2
  exit 1
fi

node scripts/with-app-env.mjs vite build --config vite.apk.config.ts
npx cap sync android

if [ -d android ]; then
  printf 'sdk.dir=%s\n' "$SDK_ROOT" > android/local.properties
  (cd android && ./gradlew :app:assembleDebug --no-daemon)
  APK="$(find android/app/build/outputs/apk -name '*-debug.apk' | head -1)"
  mkdir -p public dist-apk
  cp -f "$APK" public/hierarchy-debug.apk
  cp -f "$APK" dist-apk/hierarchy-debug.apk
  echo "APK $APK"
  echo "copied to public/hierarchy-debug.apk"
fi
