#!/usr/bin/env bash
# 重启后自动补齐抓包环境再触发 KG 客户端（配合 scripts/kg_mock.py passthrough）。
# 用法: ./kg_boot_capture.sh
# 前置: mitmdump 已在 8443 起（KG_MOCK=0 透传），宿主 /etc/hosts 已指到 127.0.0.1。
set -uo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
LOG=/tmp/kg_boot.log
: > "$LOG"
log() { printf '[%s] %s\n' "$(date +%T)" "$*" | tee -a "$LOG"; }

CAP=/tmp/cap.log
started=$(grep -c "gksl/v1/lookup" "$CAP" 2>/dev/null || echo 0)
log "重启前 lookup 计数=$started"

adb reboot >/dev/null 2>&1
adb wait-for-device >/dev/null 2>&1
log "设备回来了，等 boot_completed"
for _ in $(seq 1 60); do
  [ "$(adb shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" = 1 ] && break
  sleep 2
done

# 拿 root（走 temp_root.py，成功判据是 su 可用）
log "取 root"
(cd "$ROOT" && ./scripts/temp_root.py --retries 1 --log /tmp/tr_boot.log >/dev/null 2>&1)
for _ in $(seq 1 30); do adb shell "su -c true" >/dev/null 2>&1 && break; sleep 3; done
if ! adb shell "su -c true" >/dev/null 2>&1; then
  log "拿不到 root，放弃"; exit 1
fi
log "root 就绪"

# 恢复环境：CA bind、iptables 放行 + 全局重定向、adb reverse
su_() { adb shell "su -c '$*'"; }
su_ "cp -a /system/etc/security/cacerts /data/local/tmp/cacerts3 2>/dev/null; cp /data/local/tmp/c8750f0d.0 /data/local/tmp/cacerts3/; mount --bind /data/local/tmp/cacerts3 /system/etc/security/cacerts" >/dev/null 2>&1
su_ "sysctl -w net.ipv6.conf.all.disable_ipv6=1" >/dev/null 2>&1
for ip in $(dig +short pinning-02.secb2b.com A stage-pinning-02.secb2b.com A | grep -E '^[0-9.]+$' | sort -u); do
  su_ "iptables -t nat -I OUTPUT -d $ip -p tcp --dport 443 -j RETURN" >/dev/null 2>&1
done
su_ "iptables -t nat -A OUTPUT -p tcp --dport 443 -j REDIRECT --to-port 8443" >/dev/null 2>&1
adb reverse tcp:8443 tcp:8443 >/dev/null 2>&1
log "环境已补（iptables/reverse/CA）"

# 起网络：start_on_network_availability 已在 prefs 置 true，网络回调应触发一次
pkill -f gnirehtet >/dev/null 2>&1
(cd /tmp/ghj/gnirehtet-java && nohup java -jar gnirehtet.jar run > /tmp/gh_boot.log 2>&1 &)
log "gnirehtet 起，等网络"
for _ in $(seq 1 20); do
  [ "$(adb shell "curl -s -m 5 -o /dev/null -w '%{http_code}' https://example.com" 2>/dev/null | tr -d '\r')" = 200 ] && break
  sleep 3
done

# 主动触发一次
su_ "am force-stop com.samsung.android.kgclient" >/dev/null 2>&1
su_ "/data/adb/ksu/bin/resetprop knox.kg.state Checking" >/dev/null 2>&1
su_ "am broadcast -a android.intent.action.BOOT_COMPLETED -n com.samsung.android.kgclient/.receiver.SystemIntentReceiver" >/dev/null 2>&1
su_ "am broadcast -a com.sec.android.app.setupwizard.SETUPWIZARD_COMPLETE -n com.samsung.android.kgclient/.receiver.SystemIntentReceiver" >/dev/null 2>&1

log "开始观察 180s（lookup 计数 / kg.state）"
for _ in $(seq 1 36); do
  sleep 5
  n=$(grep -c "gksl/v1/lookup" "$CAP" 2>/dev/null || echo 0)
  s=$(adb shell "su -c getprop knox.kg.state" 2>/dev/null | tr -d '\r')
  log "lookup=$n state=$s"
  [ "$n" -gt "$started" ] && { log "捕获到新的 lookup！"; break; }
done
log "结束"
