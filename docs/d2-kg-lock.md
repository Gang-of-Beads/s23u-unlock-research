# D2 错误与 KG 锁定 —— 事故记录与恢复要点

记录于 2026-11-13。**这是目前最危险的一条岔路，动 KG 状态前先读这份。**

主线只有一条：**让 KG 进入闸门认可的状态**——`-5` 是 KG 的内容校验，不是解锁状态。
反汇编出的闸门表只放行 **1(Checking)/4**，`Active(2)`/`Locked(3)` 都拒（`findings.md` 第 23 条）。
状态不到位之前，刷任何 custom 镜像都是白费一次 Download 会话。

## 保命守则（避免再次把自己锁死）

1. KG 处于 `Active` 时，**保持联网 + 三星账号登录**状态，这是最脆弱的资产。
2. **不要 `killall kgtaserv`、不要反复 `resetprop knox.kg.state`**——本次锁死就是这么来的。
3. 尽量**不要设 PIN**（会让 D2 回归）；确需进 Download 时用
   `cmd lock_settings clear --old <pin>` + `cmd lock_settings set-disabled true` 临时切走。

## D2 是什么

One UI 8.5（2026 年更新）起，三星给 Download 模式加了门禁：**只要设备设了锁屏安全
（PIN/密码/图案/生物识别），按标准组合键进 Download 就会立刻报
`[Reboot Device - D2]`，并且 `USB 完全不枚举`**，Odin/heimdall 都连不上。
社区把这叫「D2 错误 / non-download 模式」。

- 进入 Download 的正确组合键是：关机 → **同时按住音量上+音量下** → 保持按住**插 USB** →
  Warning 屏后松手 → 按音量上进 Download。（网上大量教程写成「音量下+电源」是错的）
- 但只要**有锁屏安全**就必然 D2，所以 D2 不是按键问题。
- 已知规避：把锁屏改回「无」（会清生物识别，不清数据）；或者先开 **Maintenance Mode**。
  两者**都需要能进系统**。

来源：XDA「Bypass Samsung's New 2026 D2 Error…」（4792462）、DroidWin 同名文章、
XDA A566B 报告（D2 时 USB 不出现，recovery/正常启动都正常）。

## 我们是怎样把机器搞进 KG 锁定的

当天为了绕 KG 验证，做了这些（都在 root 下）：

1. `resetprop knox.kg.state Normal/Checking` 反复改状态
2. `killall` / `ctl.stop kgtaserv`（KG HAL）— **HAL 崩溃后 oneshot 不会自己回来**
3. 第一次 `killall` 之后状态直接变 **`knox.kg.state = Locked`**，锁屏变成
   `Phone locked / Your phone is locked because Device Services was uninstalled without authorisation.`

结论：**不要随手 kill kgtaserv / 不要反复伪造 kg.state**，KG 会判定 Device Services 被未授权移除并锁机。

## KG 锁屏的实际行为（重要）

- 它是**系统锁屏（Bouncer）**被 KG 接管，输入框是 PIN。
- **输入设备 PIN 无效**：先试 0000/1234/1111 全失败；后来完整重设向导并**新设 PIN，仍然失败**。
  → 这个 PIN 是 KG 侧（TZ/服务器）的，不是设备凭据。
- **失败计数会累积并拉长冷却**：1 小时 → **23 小时**。所以别乱试，想清楚再按。
- 锁屏上**拉不下通知栏**，也进不了设置/开发者选项。
- 工厂重置**不会**清掉这个锁（实测重置两次，锁仍在；副作用是数据没了）。

## 恢复通道现状

| 通道 | 状态 |
| --- | --- |
| Download/Odin | 被 D2 挡住（因为锁屏安全存在） |
| Recovery | 本版只有三项：`Reboot system now` / `Wipe data/factory reset` / `Power off`；**没有 Apply update from ADB（无 sideload）** |
| Android + adb | 工厂重置会清掉 `adb_enabled`，而开启 USB 调试需要 UI → 锁屏下拿不到 adb |
| USB 枚举 | 正常系统下会枚举（`04e8:6860`）；D2 屏幕上完全不枚举；Recovery 菜单页也不枚举 |

即：**所有通道互相依赖同一个前提——能进系统并操作 UI**。

## 下次的顺序建议（已统一到 KG 主线）

主线只有一条：**让 KG 进到 1/4**。状态不到位时，任何刷 custom 镜像的尝试
都注定 `-5`，重走解锁也只是改 UI，不解决根因（`findings.md` 第 2、17 条）。

1. 工厂重置后，在设置向导**第一步先连 Wi-Fi 并登录三星账号**（KG 是服务器侧状态，
   只连网不登录会一直 `Checking`→再锁死）
2. 设不设 PIN 都行，但**先别去动 KG 状态/HAL**；要进 Download 就先切「无 PIN + `set-disabled true`」
3. 拿到 `Active` 后**先做只读取证基线**（`evidence/` 已有模板），再谈下一步
4. 两条路：**(a) 机主/租户在 KG 侧放行/登记**（首选）、**(b) 拿签名 EM token**（`tooling.md` runbook）
5. 只有 KG 进到闸门认可的 **1/4**（反汇编表，`findings.md` 第 23 条）后，才刷打过 KernelSU 的 `init_boot`
6. 解锁（写 RPMB）排在持久 root 之后，别提前烧光精力

## 附：当天无效的尝试（别重复）

- `cmd lock_settings set-pin/clear`（能改设备凭据，但 KG 锁屏不认）
- `wm dismiss-keyguard` / `keyevent 82`
- `am broadcast MASTER_CLEAR`（返回 0，但没生效）
- 重置后试图用新设 PIN 解锁（失败，且吃掉了 23 小时冷却）

## 2026-11-13 下午：状态自己恢复了，以及新的边界

### 1) KG 锁**不是**永久的

在「重置 + 向导里连 Wi-Fi + 走完设置」之后，`knox.kg.state` 从 **Locked 变成了 `Active`**，
锁屏消失、直接进桌面。

**关键：这一步是靠「真正登录了三星账号」做到的**（本次是找机主登录的），不是单纯连 Wi-Fi。
KG 是服务器侧状态，必须让设备以**账号身份**去服务器核对；之前只连 gnirehtet/Wi-Fi 时
状态一直卡在 `Checking`→`Locked`，登录账号后立刻变 `Active`。

结论要点：

- 解 KG 锁的**必要条件**：能进设置向导 + 真网络 + **登录三星账号**；
- 期间**不要试 PIN**（失败计数会累加到 23 小时）；
- 恢复后 `adb_enabled` 这次是 1（能直接 adb），比上一次幸运——上一次它是 0，导致完全没有 shell；
- 登录账号意味着设备现在**真的在 KG 里登记为 Active**，所以想再往前走，
  也许需要在机主的三星/KG 侧把该设备「移出/放行」，这比纯 Android 侧折腾更靠谱。

### 2) `-5` 的确切含义（已坐实）

KG 状态的放行梯度：

| KG 状态 | 刷**原厂**分区 | 刷**改过**的镜像 |
| --- | --- | --- |
| Locked | ✗（全部 `-5`） | ✗ |
| **Active** | ✓（实测 MISC 原厂 bin 成功，无 `-5`） | **✗（实测打过 KernelSU 的 `init_boot` 仍 `-5`）** |
| 1(Checking) / 4 | ✓ | ✓（`FUN_000742f0` 闸门表放行；见 `findings.md` 第 23 条） |

所以 `All binaries are not allowed to be flashed due to KG locked` 里的 “binary” 是**签名/内容**
层面的判定：`Active` 只信原厂内容，改过的镜像必须等 KG 进到 **1 或 4**。
（prop `knox.kg.state` 只有 Prenormal/Checking/Active/Locked/Completed/Error 六个值，
字面上的 “Normal” 只是 UI 说法，闸门看的是数字。）

补充：把 `MISC` 刷成全 0 也会被拒（`-5`）——因为内容不再原厂。所以清 BCB 只能用
`Wipe data/factory reset`，别指望刷零。

### 3) D2 的规避手段已验证

`cmd lock_settings set-disabled true`（锁屏直接禁用、不设任何凭据）之后，
**连续多次** `adb reboot download` 都正常进了 Downloading，没有 D2。
这是目前唯一可脚本化的规避方式，做实验前先执行它。

### 4) 打补丁的正确姿势（踩过的坑）

设备上的 `ksud`（由 Root My Galaxy 投放）**不带 assets**，`ksud boot-patch` 直接报
`asset not found: android13-8_kernelsu.ko`。正确做法是在 Mac 上用上游 KernelSU-Next 产物：

```bash
curl -L -o ksud https://github.com/KernelSU-Next/KernelSU-Next/releases/download/v3.4.2/ksud-aarch64-apple-darwin
curl -L -o android13-5.15_kernelsu.ko https://github.com/KernelSU-Next/KernelSU-Next/releases/download/v3.4.2/aarch64_android13-5.15_kernelsu.ko
chmod +x ksud
./ksud boot-patch -b init_boot.img --kmi android13-5.15 --allow-shell -o out/
```
`--kmi` 用上游命名（`android13-5.15`），不是三星的 `android13-8`。

注意：上游 ko 是否兼容三星改过的 5.15 尚未验证（Root My Galaxy 用的是 AFZH3 专用 ko）。
若刷入后起不来，直接刷回原厂 `init_boot` 即可。

### 5) 刷写会话的现实

- 每次失败后握手失效，**必须重启回系统再重新进 Download**，不能原地重试。
- 刷原厂 `MISC`（带 BCB）会把设备打进 recovery；recovery 只有三项，出不来就 `Wipe data/factory reset`。

## 补充：设备 PIN 与 KG PIN 不是一回事（实测）

- KG 锁屏校验的 **不是** `locksettings` 里的设备凭据。曾在校准状态下
  `cmd lock_settings set-pin 1234` 设好 PIN，KG 锁屏输 1234 仍旧失败。
- KG PIN 由 **Knox Guard 服务器侧**在触发锁定时下发（机主/供应商从 KG 门户取得），
  盲猜无用，且失败计数会累积（1h → 23h）。
- 设备 PIN 的真实作用只有两个：日常解锁、以及**它会让 D2 出现**。
- 因此 `set-pin` 与「无 PIN + `cmd lock_settings set-disabled true`」是**互斥**的：
  设了 PIN 后 `set-disabled true` 会被忽略、D2 立刻回归。
  需要 Download 就先 `cmd lock_settings clear --old <pin>` 再 `set-disabled true`。

## KG 锁屏的 PIN 到底是什么（查证结果）

**不是设备 PIN，也不能在手机上设置。** 它是 **Knox Guard 后台生成的 8 位 PIN**，属于 KG 的
“PIN Unlock” 功能（官方 KBA：`docs.samsungknox.com/admin/knox-guard/kbas/how-to-unlock-a-device-using-a-pin-in-kg/`）。

官方流程：

1. 设备被 KG 锁定时，锁屏上会出现一个 **passkey**（若策略没把 PIN Unlock 放到首屏，
   passkey 在锁屏的 **Support** 页——我们当时看到的就是 `Support`）；
2. 用户把 passkey 报给 KG 管理员；
3. 管理员在 KG 控制台 **Devices → Device Status 列的 PIN 图标** → 输入 passkey、勾选确认付款 →
   系统给出 **8 位 PIN**；
4. 用户在锁屏输入该 PIN 解锁（离线可用）。

**机主可以走的另外两条路**（账号登录那条已验过，这里只记另外两条）：

- **② passkey → 租户管理员 → 8 位 PIN**：锁屏出现 `Support` 说明 PIN Unlock 可用。抄下 passkey，
  交给该设备所属 KG 租户的管理员（通常是卖机的商家/运营商），管理员在控制台生成 PIN。
  机主单靠自己走不了这条，必须能联系上租户。
- **③ 三星客服兜底**：带购买凭证，按 IMEI / 序列号申请解除 KG 锁。周期长，但不需要租户关系。

要点：

- 「Allow PIN code unlock」在 KG 策略里**默认开启**，所以锁屏一定有 PIN 输入框；
- passkey **只在锁定状态显示**，所以下次被锁时**第一件事是先抄下 passkey**，再去找管理员；
- 这套流程要求设备属于某个 KG 租户、且你能联系到该租户的管理员（卖机器的商家/运营商）。
  这也解释了为什么盲猜 0000/1234/1111、以及自己设的设备 PIN 全都无效。
- Download 界面上的 `KG STATUS: LOCKED(01)` 里的 `01` 不是 passkey，是锁类型码。

## 隐藏授权屏（OTP/QR）——D2 其实还有第三条路

来源：`soumarcelino/Samsung-D2-Hidden-OTP-QR-Gate-to-Download-Mode`（SAFZI1/ZZI8 证据，同机型）。

**在 D2 错误屏上按住 Power 不放**，然后：

1. Vol+ ×8
2. Vol- ×5
3. Vol+ ×9

（每次都要松开音量键，Power 全程不松；按错或松 Power 就重来）

22 次后会打开隐藏授权屏：显示用于本会话的 QR，和 8 位 OTP 输入框（Vol 移动、Power 确认、BACKSPACE 删除）。
输对 → **本会话可以进 Download Mode**；连错 3 次 → 会话结束，重开会生成新 QR。

要点：

- QR 里是 SI + 32 字节 UEFI RNG nonce，外层 RSA-4096-OAEP；固件里**只有公钥**，离线造不出 OTP。
- 所以这条路的用法是**找人代签**：把屏幕上这个 QR 发给有权限的一方（服务中心/代签商家），
  拿回 8 位数输入即可，不需要清数据、不需要拔卡。
- 它不改变存储的锁定状态，只放行当前会话。

对比我们原来的结论（设 PIN 与 Download 互斥）——这条通道让"有锁屏 + 要进 Download"可以共存，
值得作为 D2 的首选处理方式记录。

### 实测补充（2026-11-16）

KG `Active`、Wi-Fi 开、`locksettings get-disabled = true` 的前提下：

1. `locksettings set-pin 1234` → 成功；
2. `adb reboot download` → 设备**完全没有 USB 枚举**（`adb devices` 空、`ioreg` 无 `04e8`），
   即停在没有 USB 的 D2 类错误屏。

这点很重要：D2 屏**不枚举 USB**，所以隐藏 OTP 屏的数字必须**在机器上用手按音量键输入**，
不能靠 PC；也正是"设了锁屏就进不了 Download"的物理原因。

### 已确认存在（2026-11-16，AFZH3）

按上面 22 键序列操作后，屏幕**确实出现 QR 码 + 选项菜单**。也就是说：

- 该隐藏授权屏在我们这台 AFZH3 上**可用**，不是某个构建的都市传说；
- 它是 D2 死锁（设 PIN ⇒ 无法进 Download）的正解方向：**QR 找有权限方换 8 位数**，
  不用清数据、不用拔卡、不动 KG；
- 会话只放行当次，且连错 3 次作废，重开会换新 QR。

需要保留的证据：QR 图（拍照）+ 当时的固件版本，方便后续找代签或复现。

**本次实机信封已入库**：`evidence/20261116-d2-otp/`（QR 原文 + `envelope.bin` + 说明）。
解码结构确认为 **541 字节 = 29 字节明文头 + 512 字节 RSA-4096 OAEP 密文**，
头部是 `D2` + PID `10004` + 版本 `S918BXXSAFZH3` + 反引号填充（固定宽度），
与文档字段表一致；OTP 只能私钥侧算，本地拿不到。
