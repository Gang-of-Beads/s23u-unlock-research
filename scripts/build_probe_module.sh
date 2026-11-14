#!/usr/bin/env bash
# 生成并推送根探针模块（KernelSU module），装进管理器后可让某个 stage 脚本以 root 运行。
# 用法: ./build_probe_module.sh              只生成 + 推送到 /sdcard/Download
#       ./build_probe_module.sh --job 'id'   把 post-fs-data.sh 换成自定义命令
set -euo pipefail

JOB='
OUT=/data/local/tmp/mroot.log
echo "post-fs-data uid=$(id -u) dom=$(cat /proc/self/attr/current) t=$(date)" >> "$OUT"
for p in param persist misc; do printf "%s " "$p" >> "$OUT"; sha256sum "/dev/block/by-name/$p" >> "$OUT"; done
'

while [ $# -gt 0 ]; do
  case "$1" in
    --job) JOB="$2"; shift 2 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

cat > "$tmp/module.prop" <<'EOF'
id=rcprobe
name=rcprobe
version=2
versionCode=2
author=pi
description=root probe (writes /data/local/tmp/mroot.log)
EOF

printf '#!/system/bin/sh\n%s\n' "$JOB" > "$tmp/post-fs-data.sh"
for s in late-load service boot-completed; do
  printf '#!/system/bin/sh\necho "%s uid=$(id -u)" >> /data/local/tmp/mroot.log\n' "$s" > "$tmp/$s.sh"
done
chmod 755 "$tmp"/*.sh

out=/tmp/rcprobe.zip
rm -f "$out"
( cd "$tmp" && zip -qr "$out" . )

adb push "$out" /sdcard/Download/ >/dev/null
adb shell "am broadcast -a android.intent.action.MEDIA_SCANNER_SCAN_FILE -d file:///sdcard/Download/rcprobe.zip" >/dev/null 2>&1 || true
echo "已生成并推送: /sdcard/Download/rcprobe.zip"
echo "在 KernelSU 管理器里装（Module → Install → My Files → Download → rcprobe.zip → Done → OK）"
