# 可复现流程（SM-S918B / XSG）

前提：macOS + 数据线，设备能被 `adb` 与 `lsusb` 等价物（`ioreg`）看到。
所有 Download 进入都用手机按键：**关机 → 同时按住音量上 + 音量下 → 插 USB** →
Warning 屏松手 → **短按音量上**。
注意：网上教程的「音量下 + 电源」是错的；ONE UI 8.5 下若设了锁屏安全还会直接 D2
（见 `d2-kg-lock.md`）。

## 0. 工具准备

见 `tooling.md`。产物路径：

- heimdall：`/tmp/heimdall2/build/bin/heimdall`（自编，2.2.2）
- Bifrost：`/tmp/bfapp/Bifrost.app`（仅用来下固件）

## 1. 确认目标为解锁态

```
adb shell getprop ro.boot.warranty_bit      # 1 = 曾熔断
adb shell getprop ro.product.model          # SM-S918B
```

注意：`warranty_bit=1` **不等于**已解锁。看到下面这组矛盾就是「解锁半完成态」：

- 已有：`warranty_bit=1`、`ulcnt` 涨过、开发者选项里 `OEM 解锁` 项消失
- 仍有：`verifiedbootstate=green`、`ro.boot.other.locked=1`、`ro.boot.vbmeta.device_state=locked`

补充（**KG 主线**）：刷副本镜像被 `-5` 拒，根因是 KG 内容校验，不是解锁半完成（`findings.md` 第 17 条）。
所以 §1b 现在**降级为备查**；主线是先确认 `getprop knox.kg.state`：

- `Locked` → 只能刷原厂，先按 `d2-kg-lock.md` 恢复；
- `Active` → 也只放行原厂内容，需要让 KG 进到闸门认可的状态（反汇编是 **1(Checking)/4**，
  不是字面上的 "Normal"）才可能刷 patched `init_boot`；
- 状态 1/4 → 才可能刷 custom 镜像（`init_boot` 补丁命令见 `d2-kg-lock.md`）。
  闸门表见 `findings.md` 第 23 条。

## 1b. 重走解锁（**注：KG 不放行时它不解决 `-5`**，留作写 RPMB 的备查步骤）

1. `adb reboot download`（或按键：关机 → 音量上+音量下 → 插 USB → Warning 屏松手 → 音量上）。
2. 入口页**长按音量上** → 出现确认页就再按一次音量上。
3. 设备清数据并重启。
4. 验证：`adb shell getprop ro.boot.verifiedbootstate` 应变为 `orange`（或 `other.locked` 变 `0`），
   且此时再刷副本镜像应不再报 `-5`。

代价：数据再一次被清空。

## 2. 取 One UI 8.5 固件

版本：`S918BXXSAFZH3/S918BOXMAFZH3/S918BXXSAFZE1`

Bifrost 里 Model `SM-S918B`、Region `XSG`，版本栏填上面 4 段式：
`S918BXXSAFZH3/S918BOXMAFZH3/S918BXXSAFZE1/S918BXXSAFZH3`。

磁盘需求约 60 GB 空闲（16 GB 包 + 18 GB 解包镜像）。

## 3. 比对 PIT（必须）

```
unzip -o -q *SAFZH3*.zip CSC_OXM*.tar.md5
tar -xf CSC_OXM*.tar.md5 *.pit
# 设备侧：进 Download 后
heimdall print-pit --no-reboot > /tmp/pit.txt
# 逐项比名称 + 块数，必须零差异
```

本次结果：109 项一致。不一致就停，按新 PIT 重做映射。

## 4. 解包与建映射

```
unzip -o -q *SAFZH3*.zip "BL_*.tar.md5" "AP_*.tar.md5" "CP_*.tar.md5"
/tmp/bfstudio/build/src/cli/bifrost-cli print-pit *.pit > /tmp/newpit.txt
python3 scripts/prep_fw.py        # 生成 /tmp/flashplan.json，未映射项应只有 fota.zip
```

## 5. 刷机（两段会话）

`scripts/sess1.sh` = BL 31 个分区，`scripts/sess2.sh` = AP/CP/CSC 其余 17 个。
先 BL、后其余，每次都要重新进 Download。

```
# 每段之前：adb reboot download（有 adb 时）或按 §0 的键
heimdall flash --ABL ... --VK ...        # sess1
# 设备会自己重启，回到 Download 后
heimdall flash --BOOT ... --OPTICS ...   # sess2
```

收尾报 `Failed to receive reboot confirmation` 属正常（设备已重启）。
若卡在 `No connection to an IOService`，等 20 秒直接接下一段。

刷完首次开机会因 MISC 里的 BCB 进 recovery → 做一次 `factory data reset`
→ `reboot system now`。

## 6. 校验降级结果

```
adb exec-out getprop ro.build.display.id    # BP4A.251205.006.S918BXXSAFZH3
adb exec-out getprop ro.build.version.release  # 16
```

## 7. 取临时 root（完整版与硬限制见 `temp-root.md`）

1. 装 `Root-My-Galaxy-SM-S918B-0.6.0.apk`（release，sha256 `0fc93c71…e16d93`）。
2. 装 Shizuku，启动服务：`adb shell <nativeLibDir>/libshizuku.so`。
3. 打开 Root My Galaxy → 顶部 KernelSU 卡片 → 走 4 步安装流程 → 预期
   `Root achieved in N seconds` / `KernelSU Next active and verified`。

## 8. 持久化（进行中）

1. 装 `KernelSU_Next_v3.4.0_33294-release.apk`（管理器）。
2. 把 `init_boot.img`（固件原版）和 AFZH3 专用 `kernelsu.ko` 推到 `Download/`。
3. 管理器首页 Install → Select a file 选 `init_boot.img` → Advanced 开
   `Always grant root to Shell`、`Force enable adb on boot` → Next → 产出
   `Download/kernelsu_next_patched_*.img`。
4. 拉回本地 → 进 Download → `heimdall flash --INIT_BOOT <patched>` → 重启 → 验 `su -c id`。

已知问题：未真正解锁时 `INIT_BOOT` 单分区必报 `-5`（响应帧 `ff ff ff ff fb ff ff ff`），
且重启后 `su` 仍不存在。先做 §1b 再回到这里。

## 回滚

回 One UI 9：重下 `S918BXXUAGZIF` 全套，按 §3–§5 再来一遍（二进制位同为 `A`，不受 SW REV 阻挡）。
