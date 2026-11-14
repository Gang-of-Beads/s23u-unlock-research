# 硬件与固件信息

采集时间：2026-11-12，采集方式：`getprop` / `proc` / `dumpsys`（当时取过临时 root，
部分 `/sys` 节点仍因 SELinux 读不到，已标注）。

> 含序列号与设备唯一 ID，仓库若公开需注意。

## 整机

| 项 | 值 |
| --- | --- |
| 机型 | `SM-S918B`（Galaxy S23 Ultra，国际/中东版，公版 dm3q） |
| 设备代号 | `dm3q` / product `dm3qxxx` |
| 序列号 | `R5CWAXXXXX` |
| AP serial | `0x000004376D249F29` |
| Samsung DID | `2004376D249F2911`（em.did） |
| CSC / sales code | `XSG`（阿联酋） |
| 硬件版本 | `ro.boot.revision = 13`，subpcb `8`，slavepcb `3` |
| 颜色/存储 | 未记录（外观为黑色系） |

## SoC / 平台

| 项 | 值 |
| --- | --- |
| SoC | Qualcomm `SM8550`（Snapdragon 8 Gen 2，Kalama） |
| `ro.soc.manufacturer` | `QTI` |
| 平台标识 | `ro.board.platform = kalama`，`ro.hardware = qcom` |
| 安全启动版本 | `ro.boot.svb.ver = SVB1.0` |
| CPU 页大小 | 4096 |
| CPU | 8 核（Cortex-X3 `0xd4e` / A715 `0xd47` 等），CPUv8 + bti/paca/pacg |
| 内核 | `5.15.189-android13-8-33413713-abS918BXXSAFZH3`（GKI 风格，Samsung 补丁） |
| KMI | `android13-8` |

## CPU

8 核 ARM64（`implementer 0x41` = ARM），3 个 cpufreq 簇，调频器 `walt`（Qualcomm）。

| 簇 | 覆盖核心 | `cpuinfo_max_freq` | 调频器 |
| --- | --- | --- | --- |
| policy0 | cpu 0–2（3 核） | 2,016,000 kHz（2.0 GHz） | walt |
| policy3 | cpu 3–6（4 核） | 2,803,200 kHz（2.8 GHz） | walt |
| policy7 | cpu 7（1 核） | 3,360,000 kHz（3.36 GHz，Prime） | walt |

`/proc/cpuinfo` 报出的 `CPU part` 与簇分布不完全对齐（内核把 0–2 标成 `0xd46`、
3–4 标 `0xd4d`、5–6 标 `0xd47`、7 标 `0xd4e`），按 ARM 部件号对应为
Cortex-A710 / A510 / A715 / X3 混合；结合簇宽（3+4+1）判断实际是
3× A510 @2.0 + 4× 大核 @2.8 + 1× X3 @3.36。variant：A710/A510 为 `0x1`，A715 为 `0x2`，X3 为 `0x1`。
特性含 `bti`、`paca`/`pacg`、`i8mm`、`bf16`。

## 存储

| 项 | 值 |
| --- | --- |
| 控制器 | UFS，`/sys/.../1d84000.ufshc`，块设备 `sda`（多 LUN：`sda`–`sdf`） |
| 逻辑块 | 4096 B |
| `sda` 容量 | 499,023,872 × 1 KiB ≈ 475 GiB（整盘名义值） |
| `/data` | 460 GiB，其中已用 5.9 GiB（当前） |
| 分区 | 105 个块设备节点，PIT 条目 109，逻辑单元 6 |
| 布局 | A-only（`boot`/`init_boot`/`vendor_boot`/`vbmeta` 均单份，无 `_b` 后缀） |

### 关键分区与容量（PIT 换算，块 4096 B）

| 分区 | 大小 | 分区 | 大小 |
| --- | --- | --- | --- |
| `super` | 10.6 GiB | `userdata` | 5.9 GiB |
| `boot` | 96 MiB | `init_boot` | 8 MiB |
| `recovery` | 104 MiB | `vendor_boot` | 96 MiB |
| `vm-bootsys` | 233 MiB | `modem` | 154 MiB |
| `vbmeta` | 32 KiB | `persist` | 0.7 MiB |

## 屏幕 / 电池

| 项 | 值 |
| --- | --- |
| 物理分辨率 | `1080x2316` |
| 密度 | 450 dpi |
| 电池技术 | Li-ion，健康度 `2`（良好） |
| 采样时电量/电压/温度 | 100% / 4.38 V / 33–35 ℃ |

## 安全/校验状态（2026-11-12）

| 项 | 值 | 含义 |
| --- | --- | --- |
| `ro.boot.warranty_bit` | `1` | Knox 位已烧，解锁动作发生过 |
| `ro.boot.ulcnt` | `3` | 解锁尝试计数 |
| `ro.boot.verifiedbootstate` | `green` | AVB 处于已验证态 |
| `ro.boot.other.locked` | `1` | 锁定 |
| `ro.boot.vbmeta.device_state` | `locked` | 锁定 |
| `ro.boot.kg` / `ro.boot.kg.bit` | `0x0` / `00` | 采集当时的值；**KG 事件后已变为 `0x2` / `01`**（见下） |
| `sys.oem_unlock_allowed` | 空 | ABL 未给出允许值，UI 里无 `OEM 解锁` 项 |

### 2026-11-13 之后的漂移

KG 事件（详见 `d2-kg-lock.md`）把引导参数也改写了，本文件上表的 KG 行已过时：

| 项 | 现值 |
| --- | --- |
| `ro.boot.kg` / `ro.boot.kg.bit` | `0x2` / `01` |
| `knox.kg.state` | `Active`（曾经 `Locked`，靠登录三星账号恢复） |
| `oem_lock 2/3` | 均回 `0`（恢复出厂抹掉了 `persistent` 里的 PDP 解锁位） |

基线快照在 `evidence/20261113-1456/`（含 `persistent` 头部 hex 与四分区 sha256）。

## 固件基线

| 项 | 值 |
| --- | --- |
| 当前构建 | `S918BXXSAFZH3`（One UI 8.5 / Android 16 / API 36），二进制位 `A` |
| 出厂/曾用构建 | `S918BXXUAGZIF`（One UI 9 / Android 17 / API 37），二进制位 `A` |
| Bootloader | `S918BXXSAFZH3` |
| 基带 | `S918BXXSAFZE1,S918BXXSAFZE1` |
| 指纹 | `samsung/dm3qxxx/dm3q:16/BP4A.251205.006/S918BXXSAFZH3:user/release-keys` |

## USB 标识

| 状态 | VID:PID |
| --- | --- |
| Download / Odin | `04e8:685d` |
| Android（MTP+ADB 复合） | `04e8:6860` – `6864` / `6868` / `686c`（随配置变化） |
| Recovery（本版无 adb） | 未枚举 |

## 取不到的信息

- `sda` 的 UFS 厂商型号/固件版本（`/sys/block/sda/device/{model,rev}` 需 root，当前 shell 被拒）
- IMEI（`service call iphonesubinfo` 在该 Android 版本上返回空 Parcel）
