#!/usr/bin/env bash
# 在 KernelSU 管理器里给某个主体授予超级用户（默认 Shell）。
# 用法: ./grant_su.sh [Shell|Termux]     # 默认 Shell
#
# 约定（见 docs/tooling.md「UI 自动化约定」）：
#   - 一律用 uiautomator dump 的 XML 定位，不截图、不按坐标瞎点；
#   - 点之前先确认前台是该 App（XML 里出现 package="com.rifsxd.ksunext"），
#     否则会点到桌面图标的长按菜单上。
set -uo pipefail

LABEL=${1:-Shell}
PKG=$([ "$LABEL" = "Shell" ] && echo com.android.shell || echo com.termux)
KSU=com.rifsxd.ksunext
D=/sdcard/u.xml

die() { echo "FAIL: $*" >&2; exit 1; }

dump() { adb shell uiautomator dump $D >/dev/null 2>&1; adb exec-out cat $D 2>/dev/null; }

# 等到前台出现指定包名（参数为空则只确保能 dump）
wait_pkg() {
  local want=${1:-} xml
  for _ in $(seq 1 10); do
    xml=$(dump)
    if [ -n "$want" ]; then
      printf '%s' "$xml" | grep -q "package=\"$want\"" && return 0
    elif [ -n "$xml" ]; then
      return 0
    fi
    sleep 1
  done
  return 1
}

# 按文本/包名找元素并点它的中心（只点可点区域内的文字节点）
tap_text() {
  local pat="$1" xy
  xy=$(dump | python3 -c '
import re,sys
t=sys.stdin.read(); pat=sys.argv[1]
m=re.search(r"(?:text|content-desc)=\""+pat+r"\"[^>]*bounds=\"\[(\d+),(\d+)\]\[(\d+),(\d+)\]\"", t)
if m:
    a,b,c,d=map(int,m.groups()); print((a+c)//2,(b+d)//2)
' "$pat")
  [ -n "$xy" ] || return 1
  # shellcheck disable=SC2086
  adb shell input tap $xy
}

# 回到确定状态：唤醒 + 解屏，再前台开管理器；被桌面长按菜单压住时按 BACK 再开
adb shell input keyevent 224 >/dev/null 2>&1    # WAKEUP，息屏时 dump 只有 systemui
sleep 1
adb shell input swipe 540 1800 540 600 150 >/dev/null 2>&1
sleep 1
adb shell input keyevent 3 >/dev/null 2>&1
sleep 1
ok=0
for _ in 1 2 3 4; do
  adb shell am start -n $KSU/.ui.MainActivity >/dev/null 2>&1
  sleep 3
  xml=$(dump)
  printf '%s' "$xml" | grep -q 'Superuser' && { ok=1; break; }
  # 只有弹窗时 dump 里会出现 Force stop 且几乎没有别的节点
  printf '%s' "$xml" | grep -q 'Force stop' && { adb shell input keyevent 4 >/dev/null 2>&1; sleep 1; }
done
[ "$ok" = 1 ] || die "管理器界面没拿到（可能被弹窗压住）"

tap_text 'Superuser' || die "找不到底部 Superuser"
wait_pkg "$KSU" >/dev/null || die "切页失败"
sleep 2

tap_text "$PKG" || tap_text "^$LABEL\$" || die "列表里没有 $LABEL（先在对应 App 里触发一次 su 请求）"
# 详情页特征：出现 App Profile
for _ in $(seq 1 8); do
  dump | grep -q 'App Profile' && break
  sleep 1
done
dump | grep -q 'App Profile' || die "没进到 $LABEL 的详情页"

# 读开关：唯一「靠右且窄」的 checkable 节点
read -r state tapxy <<<"$(dump | python3 -c '
import re,sys
t=sys.stdin.read()
best=None
for m in re.finditer(r"<node[^>]*checkable=\"true\"[^>]*>", t):
    node=m.group(0)
    b=re.search(r"bounds=\"\[(\d+),(\d+)\]\[(\d+),(\d+)\]\"", node)
    if not b: continue
    a,y1,c,y2=map(int,b.groups())
    if c-a > 260: continue                 # 排除整行可点区域
    if best and a <= best[1]: continue     # 取最靠右
    best=(("checked=\"true\"" in node), a, y1, c, y2)
if best:
    print(("on" if best[0] else "off"), f"{(best[1]+best[3])//2} {(best[2]+best[4])//2}")
' )"
[ -n "${state:-}" ] || die "没找到 Superuser 开关节点（页面结构变了？）"

if [ "$state" = "on" ]; then
  echo "$LABEL 已是 ROOT"
else
  # shellcheck disable=SC2086
  adb shell input tap $tapxy
  sleep 2
  echo "已把 $LABEL 的 Superuser 打开"
fi

adb shell input keyevent 4 >/dev/null 2>&1
if adb shell "su -c true" >/dev/null 2>&1; then
  echo "验证: adb shell su 可用"
else
  echo "验证: adb shell su 仍不可用（root 可能已失效；重取 root 后再试）" >&2
  exit 1
fi
