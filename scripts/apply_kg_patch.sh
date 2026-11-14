#!/usr/bin/env bash
# 重新把打过 pinning-bypass 的 KnoxGuard APK 装回去（**每次重启后都要跑**）。
# 背景：改过的 base.apk 会被 PackageManager 重新提取覆盖，见 docs/kg-mock.md 末尾。
# 前置：root；补丁包 /tmp/self_final.apk（本机 Mac）已存在。
set -euo pipefail
PKG=com.samsung.android.kgclient
SH="$(cd "$(dirname "$0")" && pwd)/root_exec.sh"

adb shell "su -c true" >/dev/null 2>&1 || { echo "没有 root，先跑 temp_root.py" >&2; exit 1; }
adb push /tmp/self_final.apk /data/local/tmp/self_final.apk >/dev/null
P=$(adb shell "pm path $PKG" | sed 's/package://' | tr -d '\r')
[ -n "$P" ] || { echo "拿不到 $PKG 的 APK 路径" >&2; exit 1; }

# /system 是只读，不能直接 cp；用 bind mount 顶上（文件必须 644 + root:root，否则 ART 报
# "Writable dex file ... not allowed" 直接崩）
bash "$SH" "umount '$P' 2>/dev/null
  chown root:root /data/local/tmp/self_final.apk
  chmod 644 /data/local/tmp/self_final.apk
  chcon u:object_r:system_file:s0 /data/local/tmp/self_final.apk
  mount --bind /data/local/tmp/self_final.apk '$P'
  chmod 644 '$P'
  md5sum '$P' | cut -c1-32" >/dev/null
adb shell "cmd package compile -f -m speed $PKG" >/dev/null
adb shell "su -c 'am force-stop $PKG'" >/dev/null
echo "补丁已应用：${P}（已重编译并杀进程）"
