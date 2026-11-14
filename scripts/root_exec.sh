#!/usr/bin/env bash
# 以 root 执行命令并回读输出（走 adb shell 的 su）。
# 前提: 管理器 Superuser 里 Shell 已授权（scripts/grant_su.sh Shell）+ root 仍在。
# 用法: ./root_exec.sh 'id'        执行命令行
#       ./root_exec.sh -f job.sh   执行脚本文件
set -uo pipefail

JOB=/data/local/tmp/rootjob.sh
OUT=/data/local/tmp/rootjob.out

if [ "${1:-}" = "-f" ]; then
  [ -f "${2:-}" ] || { echo "no such file: ${2:-}" >&2; exit 2; }
  body=$(cat "$2")
else
  [ $# -gt 0 ] || { echo "usage: $0 '<cmd>' | -f <script>" >&2; exit 2; }
  body="$*"
fi

adb shell "su -c true" >/dev/null 2>&1 || {
  echo "FAIL: adb shell su 不可用（Shell 未授权，或 root 已失效）" >&2
  echo "  授权: scripts/grant_su.sh Shell    重取 root: scripts/temp_root.py" >&2
  exit 3
}

{
  printf '#!/system/bin/sh\nexec > %s 2>&1\necho "uid=$(id -u) dom=$(cat /proc/self/attr/current)"\n' "$OUT"
  printf '%s\n' "$body"
  printf 'echo "rc=$?"\n'
} > /tmp/rootjob.sh

adb shell rm -f "$OUT" >/dev/null 2>&1
adb push /tmp/rootjob.sh "$JOB" >/dev/null || exit 1
adb shell chmod 755 "$JOB"
adb shell "su -c 'sh $JOB'" >/dev/null 2>&1

for _ in $(seq 1 20); do
  if adb shell "test -s $OUT" >/dev/null 2>&1; then
    sleep 0.5
    adb exec-out cat "$OUT"
    exit 0
  fi
  sleep 0.5
done
echo "TIMEOUT: 没有产出（root 可能已失效）" >&2
exit 1
