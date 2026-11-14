#!/usr/bin/env bash
# 起/停 KG MITM 全套环境（见 docs/kg-mock.md「2026-11-13 实跑记录」）。
# start 只做**环境**（CA / iptables / adb reverse / mitmdump）；APK 补丁要另外用 apply_kg_patch.sh。
# 前置：root（scripts/temp_root.py）、已把 kg_final 补丁包放在 /data/local/tmp/self_final.apk、
#       Mac 上 /tmp/kgcerts/status.json 已生成（假 enroll 应答）。
set -uo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
PKG=com.samsung.android.kgclient
LOG=/tmp/kg_mock.log
REQ=/tmp/kgreq.log
SH="$ROOT/scripts/root_exec.sh"

die() { echo "$*" >&2; exit 1; }

stop() {
  pkill -f "mitmdump --mode reverse:https://gsl.samsunggsl.com@" 2>/dev/null
  for p in 8443 8444 8445; do adb reverse --remove "tcp:$p" >/dev/null 2>&1; done
  bash "$SH" 'iptables -t nat -F OUTPUT' >/dev/null 2>&1
  echo "已清理（CA / hosts bind 仍在内核里，重启即失效）"
}

start() {
  adb shell "su -c true" >/dev/null 2>&1 || die "没有 root，先跑 scripts/temp_root.py"
  adb shell "su -c 'ls /data/local/tmp/apexcerts/c8750f0d.0'" >/dev/null 2>&1 \
    || die "缺 /data/local/tmp/apexcerts（CA 目录）"

  # 1) CA 注入到 zygote 的 mount namespace（只对 shell 注入无效）
  bash "$SH" 'for p in $(pgrep -f zygote); do nsenter -t $p -m -- mount --bind /data/local/tmp/apexcerts /apex/com.android.conscrypt/cacerts 2>/dev/null; done' >/dev/null

  # 2) 443 全量影子进 mitm；pinning 单独走 8444
  bash "$SH" 'iptables -t nat -F OUTPUT
    iptables -t nat -A OUTPUT -p tcp -d 13.35.172.47 --dport 443 -j REDIRECT --to-ports 8444
    iptables -t nat -A OUTPUT -p tcp --dport 443 -j REDIRECT --to-ports 8443' >/dev/null

  for p in 8443 8444 8445; do adb reverse "tcp:$p" "tcp:$p" >/dev/null || die "adb reverse $p 失败"; done

  [ -f /tmp/kgcerts/status.json ] || echo "警告：/tmp/kgcerts/status.json 不存在，getKGStatus 会 500" >&2
  rm -f "$LOG" "$REQ"
  PYTHONUNBUFFERED=1 nohup mitmdump \
    --mode reverse:https://gsl.samsunggsl.com@8443 \
    --mode reverse:https://pinning-02.secb2b.com@8444 \
    --mode reverse:https://eu-gslu.samsunggsl.com@8445 \
    -s "$ROOT/scripts/kg_mock.py" --set ssl_insecure=true >"$LOG" 2>&1 &
  sleep 4
  # mitm 的输出是带缓冲的，别用日志判断，直接探端口
  nc -z 127.0.0.1 8443 >/dev/null 2>&1 || die "mitmdump 没起来，看 ${LOG}"

  echo "环境就绪：日志 ${LOG} 请求 ${REQ}"
  echo "触发：adb shell su -c 'cmd jobscheduler run -f $PKG 16'"
}

case "${1:-start}" in
  start) start ;;
  stop) stop ;;
  *) echo "usage: $0 [start|stop]" >&2; exit 2 ;;
esac
