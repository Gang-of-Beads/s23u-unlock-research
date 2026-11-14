#!/usr/bin/env bash
# 编译并推送 helpers/Unrestrict.java（清 no_oem_unlock 用户限制用，见 docs/findings.md 第 14 条）。
# 依赖 android.jar + d8；可用 ANDROID_JAR / ANDROID_BUILD_TOOLS 覆盖，默认 /tmp/sdk。
set -euo pipefail

JAR=${ANDROID_JAR:-/tmp/sdk/android-35/android.jar}
BT=${ANDROID_BUILD_TOOLS:-/tmp/sdk/android-15}
[ -f "$JAR" ] || { echo "缺 android.jar: $JAR" >&2; exit 1; }
[ -x "$BT/d8" ] || { echo "缺 d8: $BT/d8" >&2; exit 1; }

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
mkdir -p "$work/src/dev/pi/unrestrict"
cp "$(dirname "$0")/helpers/Unrestrict.java" "$work/src/dev/pi/unrestrict/Main.java"
javac -source 17 -target 17 -nowarn -classpath "$JAR" -d "$work/cls" "$work/src/dev/pi/unrestrict/Main.java"
"$BT/d8" --lib "$JAR" --min-api 33 --output "$work" "$work/cls/dev/pi/unrestrict/Main.class"
( cd "$work" && zip -qj unrestrict.jar classes.dex )
adb push "$work/unrestrict.jar" /data/local/tmp/unrestrict.jar >/dev/null
echo "已推送 /data/local/tmp/unrestrict.jar"
echo "用 root 执行: CLASSPATH=/data/local/tmp/unrestrict.jar app_process /system/bin dev.pi.unrestrict.Main"
