# S23 Ultra Bootloader Unlock — Checklist

> **状态：早期通用清单，当前实现路径已被推翻。** One UI 8.5 上「OEM 解锁」项默认被
> `ro.boot.other.locked=1` 与 `knox.kg.state=Prenormal` 隐藏，且 KG 锁会把改过的镜像以 `-5` 拒刷。
> 真实情况请看 `docs/findings.md`（尤其 2、4、17）与 `docs/d2-kg-lock.md`。本文只作按键/开关参考。

参考 i01.io 小米 14 那篇的「先判可行性」思路，但三星通道完全不同：**没有 fastboot，走 Download 模式 + Odin 语义**。

## 0. 先决条件

- 数据会**全清**（恢复出厂）。先备份照片/微信/2FA。
- 解锁后 **Knox 永久熔断（warranty bit 0x1）**，不可逆：Samsung Pay / Pass / Secure Folder / Samsung Health 部分功能 / 部分银行与 DRM App 失效。
- 用能传数据的线直连 Mac，插上后选「传输文件」。macOS 无需驱动。
- `adb devices` 必须显示 `device`（不是 `unauthorized`，也不是空）。

## 1. 开开关

1. 设置 → 关于手机 → 软件信息 → 连点「编译编号」7 次。
2. 设置 → 开发者选项 → 打开 **OEM 解锁**（需联网、登录 Samsung 账号；灰着的就等几分钟或插 SIM 再试）。
3. 设置 → 开发者选项 → 打开 **USB 调试**。
4. 手机上点「允许」授权这台 Mac。

## 2. 记录现状

```sh
adb shell getprop ro.product.model          # 期望 SM-S918B / SM-S9180 等；SM-S918U* 见下方警告
adb shell getprop ro.boot.warranty_bit      # 现在应为 0
adb shell getprop sys.oem_unlock_allowed    # 应为 1
```

`SM-S918U` / `SM-S918U1`（美版）多数无 OEM 解锁选项，遇到就先停。

## 3. 进 Download 模式并解锁

```sh
adb reboot download
```

（或关机后按住 **音量上 + 音量下** 再插线。）

屏幕出现警告页后**长按音量上** → 再按一次音量上确认 `Unlock Bootloader` → 设备自动清数据并重启。

## 4. 核验

```sh
adb shell getprop ro.boot.warranty_bit      # 变成 1 = 已熔断，同时说明解锁生效
adb reboot download                          # Download 屏顶部应为 "OEM LOCK: OFF (U)"
```

解锁状态下 `adb reboot download` 会直接给出可刷分区，后续刷 Magisk / 自定义内核走 Odin 或 Heimdall。

## 5. 回锁（可选，同样清数据）

Download 模式长按音量上 → `Lock Bootloader`。注意：装过 Magisk 的机子回锁前要恢复原厂 boot 镜像，否则起不来。
