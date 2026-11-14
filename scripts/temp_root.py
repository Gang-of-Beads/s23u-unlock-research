#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""取临时 root（见 docs/temp-root.md）。成功判据：`su -c true` 真能跑。

全部界面定位走 uiautomator dump 的 XML（见 docs/tooling.md「UI 自动化约定」），不截图。
"""

from __future__ import annotations

import argparse
import logging
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree as ET

APP = "io.github.rootmygalaxy.s23ultra"
SHIZUKU = "moe.shizuku.privileged.api"
DUMP_PATH = "/sdcard/u.xml"
LOCAL_DUMP = Path("/tmp/temp_root_dump.xml")
ADB_TIMEOUT = 25
BOOT_TIMEOUT = 180
MIN_UPTIME = 75

log = logging.getLogger("temp_root")


class Ui:
    """uiautomator dump 的轻封装：只按文本/描述找节点并点其中心。"""

    BOUNDS_RE = re.compile(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]")

    @dataclass
    class Node:
        label: str
        x: int
        y: int
        checked: bool

    def __init__(self) -> None:
        self.root: ET.Element | None = None

    def refresh(self) -> bool:
        adb(["shell", "uiautomator", "dump", DUMP_PATH], check=False)
        res = adb(["exec-out", "cat", DUMP_PATH], check=False)
        if not res.stdout.strip():
            self.root = None
            return False
        LOCAL_DUMP.write_text(res.stdout, encoding="utf-8", errors="replace")
        try:
            self.root = ET.fromstring(res.stdout)
        except ET.ParseError:
            self.root = None
        return self.root is not None

    def nodes(self) -> list[Node]:
        if self.root is None:
            return []
        out: list[Node] = []
        for el in self.root.iter("node"):
            label = el.get("text") or el.get("content-desc") or ""
            m = self.BOUNDS_RE.search(el.get("bounds", ""))
            if not (label and m):
                continue
            x1, y1, x2, y2 = (int(g) for g in m.groups())
            out.append(self.Node(label, (x1 + x2) // 2, (y1 + y2) // 2, el.get("checked") == "true"))
        return out

    def find(self, pattern: str) -> Node | None:
        rx = re.compile(pattern)
        for node in self.nodes():
            if rx.search(node.label):
                return node
        return None

    def has(self, pattern: str) -> bool:
        return self.find(pattern) is not None

    def tap(self, pattern: str, *, refresh: bool = True) -> bool:
        if refresh and not self.refresh():
            return False
        node = self.find(pattern)
        if node is None:
            return False
        adb(["shell", "input", "tap", str(node.x), str(node.y)], check=False)
        log.debug("tap %s at %s,%s", pattern, node.x, node.y)
        return True

    def tap_switch_of_row(self, row_pattern: str) -> bool:
        """点某一行右侧的开关（checkable 且靠右的窄节点，同行）。"""
        if not self.refresh():
            return False
        row = self.find(row_pattern)
        if row is None:
            return False
        best: Ui.Node | None = None
        for el in (self.root.iter("node") if self.root is not None else ()):
            if el.get("checkable") != "true":
                continue
            m = self.BOUNDS_RE.search(el.get("bounds", ""))
            if not m:
                continue
            x1, y1, x2, y2 = (int(g) for g in m.groups())
            if abs((y1 + y2) // 2 - row.y) > 90 or (x2 - x1) > 260:
                continue
            if best is None or x1 > best.x:
                best = Ui.Node("switch", (x1 + x2) // 2, (y1 + y2) // 2, el.get("checked") == "true")
        if best is None:
            return False
        adb(["shell", "input", "tap", str(best.x), str(best.y)], check=False)
        return True

    def switch_state(self, row_pattern: str) -> bool | None:
        if not self.refresh():
            return None
        row = self.find(row_pattern)
        if row is None:
            return None
        for el in (self.root.iter("node") if self.root is not None else ()):
            if el.get("checkable") != "true":
                continue
            m = self.BOUNDS_RE.search(el.get("bounds", ""))
            if not m:
                continue
            x1, y1, x2, y2 = (int(g) for g in m.groups())
            if abs((y1 + y2) // 2 - row.y) <= 90 and (x2 - x1) <= 260:
                return el.get("checked") == "true"
        return None


def adb(args: list[str], *, check: bool = True, timeout: int = ADB_TIMEOUT) -> subprocess.CompletedProcess[str]:
    cmd = ["adb", *args]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired as exc:
        log.debug("adb timeout: %s", " ".join(args))
        return subprocess.CompletedProcess(cmd, 124, exc.stdout or "", "timeout")
    if check and res.returncode != 0:
        log.debug("adb rc=%s: %s", res.returncode, " ".join(args))
    return res


# ---------- 设备状态 ----------


def su_ok() -> bool:
    return adb(["shell", "su -c true"], check=False).returncode == 0


def uptime() -> int:
    out = adb(["shell", "cat /proc/uptime"], check=False).stdout.split()
    try:
        return int(float(out[0]))
    except (IndexError, ValueError):
        return 0


def wait_uptime(minimum: int) -> None:
    while (up := uptime()) < minimum:
        log.info("等 uptime（%ss/%ss）", up, minimum)
        time.sleep(5)


def wait_boot() -> None:
    adb(["wait-for-device"], check=False, timeout=BOOT_TIMEOUT)
    deadline = time.monotonic() + BOOT_TIMEOUT
    while time.monotonic() < deadline:
        if adb(["shell", "getprop", "sys.boot_completed"], check=False).stdout.strip() == "1":
            return
        time.sleep(2)


def shizuku_running() -> bool:
    return "shizuku_server" in adb(["shell", "ps -A -o name"], check=False).stdout


def ensure_shizuku(ui: Ui) -> bool:
    if shizuku_running():
        return True
    path = adb(["exec-out", "pm", "path", SHIZUKU], check=False).stdout.strip().removeprefix("package:")
    if not path:
        log.warning("找不到 Shizuku 包")
        return False
    lib = path.removesuffix("/base.apk") + "/lib/arm64/libshizuku.so"
    for _ in range(3):
        adb(["shell", lib], check=False)
        time.sleep(2)
        if shizuku_running():
            return True
    log.warning("Shizuku 起不来")
    return False


# ---------- 主流程 ----------


def wake_screen() -> None:
    """息屏时 dump 只有 systemui，先唤醒并上滑解屏。"""
    adb(["shell", "input", "keyevent", "224"], check=False)  # WAKEUP
    time.sleep(1)
    adb(["shell", "input", "swipe", "540", "1800", "540", "600", "150"], check=False)
    time.sleep(1)


def wait_ui(ui: Ui, tries: int = 10) -> bool:
    for _ in range(tries):
        if ui.refresh() and ui.nodes():
            return True
        time.sleep(1)
    return False


def close_card(ui: Ui) -> None:
    if not ui.tap("Close"):
        adb(["shell", "input", "keyevent", "4"], check=False)


def attempt(ui: Ui, timeout: int) -> bool:
    wait_uptime(MIN_UPTIME)
    wake_screen()
    wait_ui(ui)
    log.info("清后台进程")
    adb(["shell", "am kill-all"], check=False)
    for pkg in adb(["shell", "pm list packages -3"], check=False).stdout.splitlines():
        pkg = pkg.removeprefix("package:").strip()
        if pkg and pkg != APP:
            adb(["shell", "am force-stop", pkg], check=False)

    ensure_shizuku(ui)
    adb(["shell", "am force-stop", APP], check=False)
    adb(["shell", "monkey", "-p", APP, "1"], check=False)
    time.sleep(5)
    wait_ui(ui)

    if ui.has("Shizuku connection failed"):
        log.info("Shizuku 未连接，重启 Shizuku 后重试")
        close_card(ui)
        ensure_shizuku(ui)
        adb(["shell", "am force-stop", APP], check=False)
        adb(["shell", "monkey", "-p", APP, "1"], check=False)
        time.sleep(6)
        wait_ui(ui)

    if ui.has("Restart required"):
        close_card(ui)
        time.sleep(2)

    if not ui.tap("Tap to try again|Tap to install KernelSU Next|Install"):
        wake_screen()
        wait_ui(ui)
        log.warning("没有入口按钮，当前界面文本：")
        for node in ui.nodes()[:8]:
            log.warning("  %r", node.label[:32])
        return False

    time.sleep(3)
    ui.tap("Confirm")
    log.info("已确认，等结果（最多 %ss）", timeout)

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if su_ok():
            return True
        if not ui.refresh():
            time.sleep(2)
            continue
        if ui.has("Root Active"):
            return True
        if ui.has("Payload execution failed|Restart required"):
            log.info("载荷失败（内核状态已改，本机不可再试）")
            close_card(ui)
            return False
        time.sleep(3)
    log.info("等待超时")
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="取临时 root（重启失效）")
    parser.add_argument("--retries", type=int, default=1, help="失败后自动重启重试次数（默认 1）")
    parser.add_argument("--timeout", type=int, default=150, help="单次等待载荷的秒数")
    parser.add_argument("--no-reboot-on-fail", action="store_true")
    parser.add_argument("--log", type=Path, default=Path("/tmp/temp_root.log"))
    parser.add_argument("--force", action="store_true", help="即便已有 root 也重跑载荷")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="[%(asctime)s] %(message)s",
        datefmt="%H:%M:%S",
        handlers=[logging.FileHandler(args.log, "w", encoding="utf-8"), logging.StreamHandler(sys.stderr)],
    )

    # 先探测：已经有 root 就别再把正在用的 root 跑没
    if su_ok() and not args.force:
        log.info("已有 root（su 可用），跳过载荷。要强制重跑加 --force")
        return 0

    ui = Ui()
    for n in range(1, args.retries + 2):
        log.info("===== 尝试 %d/%d =====", n, args.retries + 1)
        if attempt(ui, args.timeout):
            if su_ok():
                log.info("SUCCESS: root 可用")
                return 0
            log.warning("载荷报成功但 su 不可用，尝试补授权")
            grant = Path(__file__).with_name("grant_su.sh")
            if grant.is_file():
                subprocess.run(["bash", str(grant), "Shell"], timeout=120, check=False)
                if su_ok():
                    log.info("SUCCESS: 授权后 root 可用")
                    return 0
            return 0
        if n <= args.retries and not args.no_reboot_on_fail:
            log.info("重启后重试")
            adb(["reboot"], check=False)
            wait_boot()
            time.sleep(5)

    log.error("多次尝试仍未拿到 root（日志 %s，另见 App 的 History）", args.log)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
