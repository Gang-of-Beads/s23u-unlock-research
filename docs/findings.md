# 实测结论（含坑）

按重要性排序。每条都附证据，方便复核。

> 只想看结论/现状/工具清单，读 `docs/summary.md`；这份文件是逐条证据与错误码的流水。

## 1. 三星没有 fastboot

`fastboot devices` 永远空。三星的对应物是 **Download 模式（Odin 协议，USB `04e8:685d`）**，
只有 Odin / Heimdall 能刷。`adb reboot bootloader` 也是进 Download 模式，不是 fastboot。
`adb reboot fastboot`（fastbootd）在这台机器上起不来。

## 2. 解锁状态：属性和 UI 互相矛盾，且「解锁半完成」（结论已修正；**闸门实为 KG，见第 17 条**）

**修正说明**：中期曾根据「能启动改过的 `init_boot`」判定已解锁。后续证明那些
`init_boot` 写入其实都没生效，所以该判据不成立。按现有全部证据，设备**仍然是锁定状态**，
只是被解开了一半。

### 指向「锁定」的证据

- `ro.boot.verifiedbootstate=green`、`ro.boot.vbmeta.device_state=locked`、
  `ro.boot.flash.locked=1`、`ro.boot.other.locked=1`
- 刷入任何被改过的 boot 类镜像，ABL 在提交时返回失败帧 `-5`（见第 4 条）
- 降级到 Android 16 后重扫开发者选项 129 项，仍无 `OEM 解锁` 项 —— 与 OS 版本无关

### 指向「已解开一半」的证据

- `ro.boot.warranty_bit=1`：Knox 熔断位已被烧，这一步发生在真正的解锁动作之前
- `ro.boot.ulcnt=3`：解锁尝试计数涨过
- `sys.oem_unlock_allowed` 为空、`OEM 解锁` 项从 UI 消失：ABL 认为「已允许/已解锁」，
  所以把开关藏了

### 最可能的成因

首次解锁时设备进入了「更新设备软件时发生错误」屏，**擦除没走完**。三星的解锁是两段式：
先烧 warranty 位，等擦除完成后再往 RPMB 写锁状态。擦除中断 → warranty 位烧了、
RPMB 仍是锁定 → 就是现在这个半完成态，UI 与属性各说一半。

### 因此下一步是「把 KG 补到 Normal」，不是补完解锁（结论已并入 KG 主线）

当时的推断是「重走一次解锁把 RPMB 写完」。后续实测证明**更硬的闸门是 KG**：
ABL 里那句 `All binaries are not allowed to be flashed due to KG locked` 判定的是
**内容/签名**，与解锁位无关——KG `Active` 时原厂分区能刷、改过的镜像照样 `-5`（第 17 条）。
AOSP 的 PDP 解锁位（`persistent`）ABL 根本不读，所以重走解锁只能改 UI 状态，
不会让 custom 镜像过关。

现在的主线因此是：**先把 KG 推到 `Normal`**（账号/租户侧放行，或 mock 服务器应答），
拿到 `Normal` 后才有资格谈「刷 patched `init_boot` 拿持久 root」和「重走解锁写 RPMB」。

## 2b. 属性判读备忘

`verifiedbootstate=green`、`ro.boot.verifiedbootstate`、`ro.boot.flash.locked=1`、
`ro.boot.other.locked=1`、`ro.boot.vbmeta.device_state=locked` 全都说「锁定」，
但同机同时存在 `ro.boot.warranty_bit=1`、`ro.boot.ulcnt=3`（解锁尝试计数），
且开发者选项里的 **`OEM 解锁` 项整条消失**（uiautomator 完整扫了 150 项列表，
顶底标志项都在，确认不是漏看）。

判定解锁的信号里，只有「刷入改过的 boot 类镜像不报 `-5` 且能开机」是硬的；
`warranty_bit` 只能说明「解锁动作被触发过」，不能说明已完成。
`verifiedbootstate=green` / `device_state=locked` 与 `OEM 解锁` 项消失会同时出现在半完成态，
单看任一条都会误判。

## 3. `adb reboot download` 不消耗、但 Download 会话「一次一用」

heimdall 的握手每进一次 Download 模式只被接受一次。任何一次会话结束（哪怕
`--no-reboot`）之后不重新进 Download，后续握手一律 `Failed to send handshake` /
`Protocol initialisation failed`。

**操作含义**：每次 heimdall 动作前都必须重新进 Download；Download 模式没有 adb，
只能手机按键（关机后**同时按住音量上+音量下**、插 USB，Warning 屏松手后按音量上；
注意不是「音量下+电源」）。
短按音量上是无效的，那屏的提示文案是给解锁用的）。

## 4. 改过的引导镜像被 ABL 以 `-5` 拒刷（核心坑）

- `--MISC`（0.5 MB）刷写：完全成功，`Rebooting device...` 正常，写入生效（真的进了 recovery）。
- `--BOOT`（96 MB）/ `--INIT_BOOT`（8 MB）/ `--VBMETA`（8 KB）：文件全部
  `upload successful`，但收尾 `Ending session` 收不到正常确认，
  详见下方 `-5` 响应。
- 判断写入不生效的依据：刷入 Magisk 打过补丁的 `init_boot` 后开机没有 `magiskd`；
  把 `init_boot` 写成 8 MB 的 `0xFF` 后设备照样能正常开机（说明根本没被采用）。
  这两个现象最初出现在 Android 17 上，降级后依旧（见下）。
- 同一套 heimdall、同一条线、同一个端口，`BL`（31 个分区）和 `AP`（16 个分区）
  这样的大会话反而 100% 成功——所以不是线材/带宽/传输量的问题。
- 给 heimdall 补上原始包打印后拿到确切响应：设备在 `Ending session` 回的是
  `ff ff ff ff fb ff ff ff`（`0xFFFFFFFF` = 失败帧，错误码 `-5`）。
  把收尾接收超时从 3 秒提到 120 秒，依然是 `-5`，所以**不是超时，是明确的校验拒绝**。
  位置在文件全部传完之后，即写入被接受、提交校验被拒不落盘。
- 降级到 `S918BXXSAFZH3`（Android 16）后，`INIT_BOOT` 单分区同样是 `-5`，
  说明与 Android 版本无关，与「未真正解锁」一致。
- 伴随现象：连续尝试握手会把 Download 会话搞成锁死态（实测 76 次全失败），
  只能重启设备回系统才能恢复。

判定写入是否生效的可用手段（无需 root）：刷一张会被校验的镜像，看是否 `-5`；
或刷 `MISC`（固件自带 `misc.bin` 会引导进 recovery，说明写入生效）。

## 5. heimdall 的其它行为

- 收尾默认接收超时只有 3 秒（`kDefaultTimeoutReceive = 3000`），已改为 120 秒；
  实测与故障无关，但保留无害。
- `ReceivePacket` 失败时会打印原始包（自加），用于区分「超时」与「设备拒绝」。

- 会话收尾错误不影响已传输内容在 BL/AP 这种大会话里的落盘（固件刷完能开机、构建号正确）。
- `--no-reboot` 之后设备保持 Download 模式且**不会**自己重启，需要按键。
- `Failed to confirm end of file transfer sequence` 是传输层中途断，位置随机，重试可过。
- `--resume` 只在会话还开着时有意义；会话死了会 `Failed to receive PIT file size`。
- PIT 解析按分区名精确 `strcmp`（全大写），不会模糊匹配到 `INIT_BOOT`/`VENDOR_BOOT`。
  分区大小校验用 PIT 块数，分块大小按 UFS 取 4096。

## 6. PIT 自带「flash 文件名」可用于建映射

`heimdall print-pit` 的每项都有 `Flash Filename` 字段（如 `init_boot.img` → `INIT_BOOT`），
固件 tar 里的文件名去掉 `.lz4` 后与之大小写不敏感匹配即可，不需要手工猜分区。
`scripts/prep_fw.py` 就是干这个的，未映射项会列出来（正常只有 `meta-data/fota.zip`）。

## 7. 降级可行性与做法

`S918BXXUAGZIF`（17）与 `S918BXXSAFZH3`（8.5）**二进制位同为 `A`**，
8.5 的可用构建在 FUS 上仍然齐全：`SAFZE1 / SAFZF5 / SAFZG1 / SAFZH3 / SAFZI1`。

FUS 的 `version.xml` 需要 `User-Agent: Kiss2.0_FUS`，否则 Akamai 直接 `Access Denied`：

```
https://fota-cloud-dn.ospserver.net/firmware/XSG/SM-S918B/version.xml
```

FUS 的下载鉴权（`NF_DownloadBinaryInform`）已换成新签名方案，老的
`KEY_1`/`KEY_2` 派生（samloader / samloader3）会 401。可用替代：

- **Bifrost（GUI）**：能下，版本栏可直接填 4 段式版本号。
- samfw 有 Cloudflare，curl 直取 403。

## 8. 刷 BL 前必须比对 PIT

降级换的是 BL，若分区表变了，按旧映射刷会写错位置。做法：从新固件 CSC tar 里取
`*.pit`，与设备 PIT（`heimdall print-pit` 的文本输出）逐项比对名称与块数。
本次 109 项完全一致，才继续。

## 9. Root 方案：按精确构建号适配

- `soumarcelino/Root-My-Galaxy-SM-S918B`：BOPE（CVE-2026-43499）载荷，
  按构建号分发目标，`AFZH3` 在列表内。实测一次成功（3 秒），拿到
  KernelSU-Next 控制通道（version 33294）。
- **它是临时 root**，重启即失效；持久化仍要 patch `init_boot`。
- `KernelSU-Next` 管理器「Select a file」的 LKM 补丁用的是自带通用 ko，
  Advanced 里没有指定自定义 ko 的入口；AFZH3 专用 ko 在
  `soumarcelino/KernelSU-Next-SM-S918B-AFZH3` 的 release 里
  （`android13-5.15_kernelsu.ko`，sha256 `dbb8fd27…d5763`）。
- 管理器 Advanced 里两项建议开：`Always grant root to Shell`（便于 adb 验证）、
  `Force enable adb on boot`（免得每次重启重新点 USB 授权）。

## 10. Root My Galaxy 依赖 Shizuku

它需要 Shizuku 服务作为 shell 通道。Shizuku 13.x 的启动器是 native 二进制：

```
adb shell <nativeLibraryDir>/libshizuku.so
```

成功后进程 `shizuku_server` 存在即可。UI 上的「View command」按钮被手势条遮挡，
点不到；`app_process ... rikka.shizuku.server.ShizukuService` 直接跑会 `Aborted`。

## 11. 其它零碎

- MISC 刷入固件自带的 `misc.bin` 会把设备导进 recovery，`Try again` 会循环回来，
  recovery 里做一次 `factory data reset` 才能进系统。
- `adb shell` 在刚开机时会持续 `error: closed`，改用 `adb exec-out`。
- uiautomator 能点到的 DocumentsUI 有时不响应点击；换成 Magisk 的
  「Enter image URL」+ 本地 `python3 -m http.server` 更稳定。
- 这台机器的 Download 屏是精简版，不显示 `OEM LOCK:`；但**会**显示 `KG STATUS: LOCKED(01)`、
  `RP SWREV`、`RPMB PROVISIONED`、`SECURE DOWNLOAD: ENABLE`——即 KG 状态在 ABL 判断里是一等公民。

## 12. 社区实证：One UI 8 起解锁已死，无成功案例（2026-11 检索）

检索来源：`zenfyrdev/bootloader-unlock-wall-of-shame`（三星页）、XDA、Reddit、DroidWin。

- wall-of-shame 对三星结论是「⛔ Avoid at all costs」，并写明：**One UI 8 起三星彻底废掉解锁，
  不分机型区域；已是解锁态的机器在通过 Odin 刷入 One UI 8 固件后会被自动重新上锁**。
  唯一的回退条件是 One UI 7 与 8 的二进制位相同。
- XDA「S23 Ultra 误升到二进制 9」帖，Recognized Dev 的回答：*Unfortunately, you have to say goodbye.*
- XDA「想把解锁找回来」在研帖，回复：*It's not possible to downgrade due to hardware ARB*，
  并称「Everyone on XDA already knows that since OneUI 8 beta」。
- XDA「OEM unlock is back on One UI 8.5/9」帖**结论是错的**，楼主后来自己承认误把请愿书当依据。

### 对本案的含义

我们设备已被烧到二进制 `A`，One UI 7 的构建全是 `8`/`9`，因此「回 One UI 7 换解锁」被 ARB 挡住。
本机是被「刷 One UI 8.5 固件」这个动作上锁的，不是操作失误。

### 现有生态全是免解锁临时 root

DroidWin 的 One UI 9 root 指南把 Root My Galaxy / SamSU / Uni-Root 并列，
全部基于 CVE-2026-43499、需要精确内核目标、依赖 Shizuku、**重启失效**。
其中 `dm3q-S918BXXSAFZF5` 被标注「confirmed working：完整链路含 KernelSU late-load 与已授予 su」；
本机 `AFZH3` 同样跑通（2–8 秒）。

### 临时 root 的实际可用范围

- 内核侧与管理器控制通道正常（管理器首页 `Working` / `LKM (GKI2)`）。
- **但 `adb shell` 用不了 `su`**：KernelSU 的 `/system/bin/su`（overlayfs）与 `/data/adb` 可遍历性
  由 `ksud post-fs-data` 在启动时建立；运行时注入没有这一步。
- 手动触发也失败：`/data/local/tmp/ksud-selected post-fs-data` →
  `Failed to extract bin assets: /data/adb/ksu/bin is not a regular directory`（shell 无法遍历 `/data/adb`）。
- SELinux 还额外挡着：连 `ls /data/local/tmp/temp_su.sock` 都是 `Permission denied`，shell 域连不上
  临时 root 的 socket。
- 结论（**已被第 13 条推翻，保留过程记录**）：当时认为 root 只能由应用使用。

### 因此的最终形态

放弃解锁；把「重启后重新取临时 root」固化成固定步骤，root 交给需要的 App 使用。
每次重启后需要：`adb shell` 启动 Shizuku → 打开 Root My Galaxy → 确认安装。

## 13. 临时 root 的边界（2026-11-12 实测）

- 载荷 `cve-2026-43499-app-afzh3.so` 与构建号一一对应，App 每次运行都会把
  `ksu-payload`/`ksu-helper`/`ksud-selected`/`mm-exec-factory`/`stability-launcher`
  **重新推流覆盖** `/data/local/tmp`，所以「把 `ksud-selected` 换成 wrapper」拦不住。
- `/data/local/tmp/temp_su.sock` 的 `ls -l` 与 connect 对 `shell`、`untrusted_app_27`、
  `untrusted_app` 三种域全部 `Permission denied`（SELinux）。root 只活在 App 内部。
- 自己写了个 targetSdk 36 的壳 App（`dev.pi.rootcmd`）验证上述判断：域确实是
  `untrusted_app`，也仍被拒；该壳能执行任意命令并回读，留作后续实验工具。
- root 生命周期极短：安装流程走完即 `Reboot required`、holder 退出、管理器立刻变回 `Not installed`。
- 失败的后果是**本次开机内核状态不一致**，同一开机内重试必失败；必须重启、等 ≥ 60 秒再试，
  之后基本一次过（实测 `Root achieved in 3 秒`）。App 的 History 页是唯一可信的成败判定。
- 手工直接跑 `stability-launcher`（不经 App）可过 gate、可定位内核，但三次尝试都停在
  `[preflight] mm_struct geometry/load rejected size=1024 per=32 pages=8 active=1857 total=1920 slabs=60`；
  `--conservative` 无效，杀光第三方进程后 `active` 仍为 1857（不是进程数问题）。
- 模块这条路只走通一半：管理器能在 root 窗口内以 root 跑 `ksud`（`Module → Install` 返回
  `Flash success`，模块确实进了 `/data/adb/modules`），但 `post-fs-data.sh` / `late-load.sh` /
  `service.sh` / `boot-completed.sh` 四个 stage 脚本**一次都没执行**，`mroot.log` 不出现。
  原因是没有 init 钩子去调 `ksud post-fs-data`。
- 【修正】第 13 条早先写的「root 只能留在 App 内」已被推翻：引擎跑完后 `/system/bin/su` 会就位，
  在管理器 `Superuser` 给 Termux 授权后，Termux 里 `su` 直接可用（`uid=0(root)`，域 `u:r:ksu:s0`），
  `/data/adb/ksu/bin`（含 `ksud`、`resetprop`、`busybox`）可遍历。授权是一次性的。
- 再修正：给管理器 `Superuser` 里的 **`Shell`（com.android.shell）** 授权后，`adb shell su` 直接可用
  （`uid=0(root)`，域 `u:r:ksu:s0`），`/data/adb/ksu/bin` 可遍历。**授权前 `su` 在 shell 侧连文件都看不见**
  （overlay 只挂进已授权域的 namespace，报 `No such file or directory`）——别误判成没装上。
- 因此 root 命令走 `adb shell su -c` 即可，工具：`scripts/root_exec.sh`；取 root 用 `scripts/temp_root.py`
  （它先探测 `su`，已有 root 不会重跑载荷）。
- 模块 stage 脚本仍不执行（`ksud post-fs-data` 没人调），但既然已有 root shell，
  可以直接 `ksud post-fs-data` / `resetprop` 手动跑，模块只是可选。
- 授权动作本身可以脚本化：`scripts/grant_su.sh Shell`（uiautomator XML 定位 + 读 `checked`）。
  踩过的坑：dump 只返回 `Launch`/`Force stop`/`Restart` 三条 = 桌面图标被长按弹出菜单压在顶上；
  息屏时 dump 只有 `com.android.systemui`。规则记在 `docs/tooling.md`「UI 自动化约定」：
  先 WAKEUP + 解屏 + HOME + 前台包名校验，再点；判断一律用 XML，不用截图。

## 14. OEM 解锁入口为什么消失，以及光靠框架改标志不够（2026-11-12 实测）

`SecSettings` 里 `OemUnlockPreferenceController.isAvailable()` 的判定（jadx 反编译原文）：

```java
return (SystemProperties.get("ro.frp.pst").equals("") ||
        SystemProperties.get("ro.boot.other.locked").equals("1") ||
        KnoxGuardManager.getInstance().shouldBlockCustomRom() ||
        this.mOemLockManager == null) ? false : true;
```

本机数据：`ro.frp.pst=/dev/block/persistent`（非空）、`mOemLockManager` 非空，
所以入口被隐藏只剩两个原因，实测是**后者**：

- `ro.boot.other.locked=1`（可用 `resetprop` 临时改 0）
- **`knox.kg.state=Prenormal`** → `shouldBlockCustomRom()=true`。KG 处于 Prenormal 时
  同时禁自定义二进制，这很可能也是刷改过的 `init_boot` 报 `-5` 的真因。

**另一层阻碍**：`OemLockService` 在这台机器上没有 OEM lock HAL，退化成
`PersistentDataBlockLock`，于是：

- `isOemUnlockAllowedByCarrier()` = `!hasUserRestriction("no_oem_unlock")`，
  而 `no_oem_unlock` 是**被设置着**的 → 开关始终 disabled，摘要显示
  “Connect to the internet or contact your service provider to use OEM unlock.”
- `isDeviceOemUnlocked()` 直接读 `ro.boot.flash.locked == "0"`，所以把该 prop 改 0 后
  Settings 会谎报 “Bootloader already unlocked”（记得改回 1）。

**已打通的步骤**（均为运行时、可回退）：

1. `resetprop ro.boot.other.locked 0` + `resetprop knox.kg.state Normal` → 入口出现。
2. 清掉用户限制 `no_oem_unlock`（shell 没有 MANAGE_USERS，用 root 跑 `app_process`
   调 `IUserManager.setUserRestriction("no_oem_unlock", false, 0)`）→ 开关变为可点。
3. 拨开关 → 警告弹窗 → Enable → 开关变 ON，`service call oem_lock 3` 返回 1，
   `persistent` 分区哈希改变（`28997bf…` → `508b5be…`），**重启后依旧为 1**。

**但 ABL 不认这个位**：带着该状态进 Download，屏幕仍然只有 `Downloading...`，
长按音量上毫无反应，`ro.boot.other.locked` 回来还是 1、`verifiedbootstate` 仍是 green。

说明三星真正的解锁标志是 `param`/RPMB 里由 TrustZone 写的记录（正常由 KMX + KG 状态驱动），
AOSP 的 persistent data block 位只有 Android 侧自己看。这条也解释了为什么开关“看着能用却没用”。

## 15. 每次 reboot 会被重置的东西

`knox.kg.state` 回 `Prenormal`、`ro.boot.other.locked` 回 1、`no_oem_unlock` 用户限制被重新加上
（`/data/system/users/0.xml` 会被系统重写，手工改文件无效，要在运行时调接口）。

## 16. KG 被玩坏 → 设备锁死（2026-11-13，详见 `d2-kg-lock.md`）

- 反复 `resetprop knox.kg.state` + `killall kgtaserv` 之后，TZ 把 KG 置为 **Locked**，
  锁屏变成「Phone locked / Device Services was uninstalled…」，**要 KG 侧的 PIN**，
  设备 PIN 无效，失败冷却会累积到 23 小时。
- 更致命：One UI 8.5 起**有锁屏安全就进不了 Download**（D2 错误，且 USB 不枚举），
  于是「刷机恢复」这条路也被堵住；本版 recovery 又没有 sideload。
- 工厂重置两次都清不掉该锁。
- 教训：动手做 KG 实验前，先把锁屏设成「无」；不要 `killall kgtaserv`。

## 17. KG 实测放行梯度（2026-11-13 下午）

- KG `Locked`：任何分区都 `-5`。
- KG `Active`：**原厂** 分区可刷（MISC 成功），**改过的镜像仍然 `-5`**（打过 KernelSU 的 init_boot 实测）。
- 结论：`All binaries are not allowed to be flashed due to KG locked` 判定的是**内容/签名**，
  不是分区。想让 custom 镜像过关必须先拿到 KG `Normal`。
- 另外：MISC 刷全 0 也被拒；清 BCB 只能用恢复出厂。
- 让 KG 从 `Locked` 回 `Active` 的**真实条件是「登录三星账号」**（本次由机主完成），
  单纯连 Wi-Fi 只会停在 `Checking`。KG 是服务器侧状态，必须以账号身份核对。
  期间别试 PIN（失败计数会到 23 小时）。
- 【脚本教训】取 root 前**必须先探测** `su -c true`：root 还活着时重跑载荷会把现有 root 打掉
  （载荷失败/成功都可能让 holder 退出）。`scripts/temp_root.py` 已改为探测后直接跳过，
  要强制重跑才加 `--force`。

## 18. 本地绕过（不碰服务器）的结论：全部无效

试过的本地手段与结果：

| 手段 | 结果 |
| --- | --- |
| `KnoxGuardManager.resetRPMB()` | 返 0，但 `getTAState` 仍 2、`ro.boot.kg.bit` 仍 `01`，重启后不变 |
| `setCheckingState()` | 恒返回 `-1` |
| `unlockScreen()` | 返 0，TZ 状态不动 |
| `kg30_setCheckingState` / `kg30_bindToLockScreen` / `kg30_resetRPMB` | 全 `null`（本机是 v2 HAL，KG30 老接口无效） |
| 直接调 framework | 需调用方 uid 为 `com.samsung.android.kgclient`；`Os.setuid(10096)` 可绕过（工具见 `/tmp/KG*.java`） |

ABL 侧也没有软开关（见第 17 条附带的静态追查：`-5` 只看 TZ 的 KG 状态）。
假 enroll 已能直通到 `provisionCert`，卡在 TZ 对自签证书返回 **264**。

## 19. 「降级到 One UI 7 / Android 15」这条路可行吗？——本机不行

网上（含 XDA/DroidWin）给出的标准救人步骤都是「降级回 One UI 7 再解锁」。对**还停在二进制 ≤9**
的机器成立，对本机不成立：

| 项 | 值 |
| --- | --- |
| 本机 rollback index | `ro.boot.rp = 10`（Download 屏也显示 `RP SWREV: B10/K10/S10`） |
| One UI 7（Android 15）最新构建 | `S918BXXS8FYG2`（binary 8）、`S918BXXS9FYJ1`（binary 9） |
| 本机当前构建 | `S918BXXSAFZH3`（binary `A` = 10） |

三星的二进制位到 `9` 之后用字母续（`A`=10），所以 One UI 7 的 8/9 **低于** 本机的 10，
ARB（rollback protection）会拒；这与社区「降级被 ARB 挡」的说法一致。

补充：即使跳过 BL 只刷 AP/CP/CSC，ABL 仍会按分区 rollback index 校验，同样会被拒
（典型报 `SW REV CHECK FAIL`）。KG 只是第二道闸，ARB 是更靠前的那道。

结论：要试只能等「二进制 ≥10 且行为回退到可解锁」的固件，或者走 KG 登记/放行那条路。

## 20. 解锁状态存在 `param` 里，但门是「先 KG、后解锁」（实测）

`Odin` 里存在这些串，说明 ABL 的 OEM 解锁状态是 **`param` 分区里的结构**，不是 PDP：

- `%a(%d): Cannot read param data. Type=[%d].`
- `%a(%d) : Can't Access PARAM partition(EFI_STATUS : %d)`
- `Setting is on but apdp/modem/param binary allowed`
- `OEMLOCK`、`IsUnlocked`（字段名）
- `GetKGFuseFromBL` / `GetKGFuseFromTA`

反汇编定位：

- `0x25c60` = 读 param 首字节（`0x258b0(blob,0x354,0,0)` 后 `ldrb [sp]`）；
  `0x25cb0(type)` = 读 → 把首字节写成 `type` → `0x258b0(...,w3=1)` 写回。所以 **param[0] 是状态字节**。
- `0x89a8`：`param[0] == 3` 时走另一条分支（`csinc w20, w19, wzr, ne`），
  这条在开机早段决定要不要做校验类动作。

实测：先用 root 备份 param（`/data/local/tmp/param.bak`，sha256 `3f436bb9…`），
把 param[0] 从 `0x01` 改成 `0x03`，重启。

结果：

- 设备**直接进了 Download 模式**（说明 byte0 也参与启动模式选择），
- 但刷 patched `init_boot` **仍然 `-5`**。

结论：只改首字节≠解锁。真正的解锁信息在 param 的**带类型记录**里（`OEMLOCK`/`IsUnlocked` 那一套），
要按记录格式写；首字节只是外层的状态/模式。

### param 记录格式（继续逆的结果）

- `0x258b0(buf, size, Type, mode)` 就是 param 读写器：开头 `adrp 0x9d000+0x375` 传入分区名
  **`"param"`**，用 `0x26be0` 打开；`mode` 0=读、1=写；`Type` 越界会打
  `%a(%d): Cannot read param data. Type=[%d].`，且只接受 0 和 1（调用点全部是这两个值）。
- 不同 Type 对应不同区域与不同长度：Type 0 用 0x354，Type 1 用 0x2098 等；长度来自跳转表（表在 `0xaf6ac`）。
- `0x25f2c~0x25f4c` 会读 Type 0 记录后 `orr w8, w8, #0x3` 再写回 —— 即置低两位。
- `IsUnlocked` 是 `0x112510` 结构里的 `+0xd`（`0x11251d`），但该函数两条分支都写 0，
  真正置 1 的位置还没追到。

### 关键结论：门是**先 KG、后解锁**

我们改了 param[0]=3 之后设备直接进 Download（3 = 下载/刷机模式，1 = 正常启动），
但补丁镜像仍然 `-5`，而且 ABL 打的就是 KG 那句。

说明 ABL 的判定顺序是 **先查 KG 状态**（锁定就一律拒），解锁位只在 KG 放行之后才起作用。
所以 param 这条路不能单独解决问题，必须先把 KG 弄到放行态。

## 21. `getTAInfo` 各下标的含义（框架里是明文映射）

`a7.m.z(i)` 直接给出语义，省得猜：

| 下标 | 含义 | 本机值 |
| --- | --- | --- |
| 1 | Version | 2 |
| 2 | **CertProvisioned** | **false** |
| 3 | HotpRetryCounter | 0 |
| 4 | ApSerial | `AAAA0000…249F29` |
| 5 | HotpKeyHash | null |

也就是说本机 TZ **从未 provision 过证书**，假 enroll 必须先把证书送进去；
而自签/自建链七种组合全被 TZ 以 **4097** 拒（详见 `kg-mock.md` 末节）。

## 22. 网上有没有现成 KG 证书？——没有；但找到了同代机型的深层结论

检索方式：GitHub code search（已登录 gh）、grep.app、DDG/Bing。
关键词：`kgEnrollCrt`、`kgProvisionCrt`、`kgPolicySigningCrt`、`kgBlSigningCrt`、
`MASTER_PINNING_SERVER_CERT`、`regInfoSignature`、`"All binaries are not allowed to be flashed"`。

**证书本身没有人公开过**（命中只有 KG 客户端自身的 smali 字段定义）。也就是必须自己抓。

但命中了两个非常相关的仓库：

- `ferhatsanli/samroot23` —— 同代 S23（SM-S911B），系统性地逆了 ABL 的解锁路径。
  它的结论比我们的更进一步：One UI 8（其样本 EZB6 / FZDP，二进制 B9）里，
  **ABL 的 Download 模式长按解锁入口函数被换成了无条件 `return false`**
  （`0xCA790`，28 条指令替换掉旧版 71 条动态判定），但下层长按/确认/状态切换代码仍在。
  真正的解锁切换走的是 **EM token / VaultKeeper `tz_kg KG_unlock`**，
  伴随 VB 持久写 + 重置 + 擦 userdata。
- `starlight4you/T860-ui6` —— 有整套「把 kgclient 全部组件 disable」的补丁脚本
  （manifest 禁用 + 把 processors 里一堆方法改成空实现），可作为"让客户别乱锁屏"的参考。

**对我们的两条含义**：

1. 就算把 KG 弄成 Normal，长按音量上也可能**依然没有确认页**（因为入口函数是死的）；
   但只要 TZ 侧状态是真放行的，ABL 的刷写校验仍可能放行 —— 这正是我们一直撞的 `-5` 闸门。
2. 证书只能靠抓，抓不到就只能在真机/租户侧想办法。

## 23. 用 Ghidra/REA 反出「刷写闸门」的真实判定（重要）

装了 Ghidra 12.2 + REA（MCP，见下节），直接拿到伪代码。**闸门根本不是「KG 锁就一律拒」那么简单**：

`FUN_000742f0(ctx, reason)`（0x742f0）伪代码：

```c
if (*reason == 0) {                       // 某种模式
  if (ctx->kg_status == 3 && reason[2] == 2) {
      u = FUN_000789e0(0);                // 查 EM 模式位图 bit0
      return (u & 0xff) == 0;             // 0 = 放行
  }
} else {
  if (ctx->f_15c == 1) return 1;          // 直接拒？
  if (ctx->kg_status < 6) return table[ctx->kg_status];   // 1 = 拒
}
return 0;
```

`table` 在 `0xcc194`，实测 6 个 int = **[1,0,1,1,0,1]**，按 KG 状态 0..5：

| KG 状态 | 0 Prenormal | 1 Checking | 2 Active | 3 Locked | 4 | 5 Error |
| --- | --- | --- | --- | --- | --- | --- |
| 结果 | 拒 | **放行** | 拒 | 拒 | **放行** | 拒 |

**这解释了我们全部的实测**：`Active(2)` 也是拒的，所以「KG 变 Active」从来不会让 `-5` 消失。

`FUN_000789e0(bit)` 只是 `bitmap[0x11fc60]` 的位测试；那张 32 字节位图是 **EM 模式位图**，
在 `FUN_0007c7a0`（0x7cea0）里由 EM 应答包 **bit5=「Need Update Bits」** 时从包内 `+0x90`
`memcpy` 32 字节直接写入（0x7cea0 第 234 行 `FUN_00005320(&DAT_0011fc60, pkt+0x90, 0x20)`）。

也就是：**状态 3（Locked）下唯一的本地逃生口是 EM 模式位 0**（工程模式 / EM token）。
这也和网上那个同代 S23 仓库提到的「EM token 是唯一授权路线」对上了。

## 24. 网上关于「8 Gen 2 漏洞」的实际收获：EDL 路存在，但入口要动硬件

平台是 **SM8550（Snapdragon 8 Gen 2）**。围绕这条线查到三件事：

1. **CVE-2026-25262** —— Qualcomm Sahara 协议里的 write-what-where，可在**绕过签名校验**的前提下
   往 SRAM 写任意值，从而加载**未签名**的 firehose loader。
   研究仓库：`shurikgo/cve-2026-25262-sm8450-research`（在 SM8450/POCO F4 GT 上验证了任意写，
   且指出认证开关是 loader 里 `0x6b9cd538` 的 64 位字段）。SM8550 同属 ARMv9 世代，适用性待验。
2. **本机型号的 EDL loader 是公开的**：`Alephgsm/SAMSUNG-EDL-Loaders` 有
   `Samsung Galaxy S23 Ultra (SM-S918B)/firehose/SM-S918B_prog_firehose_ddr.elf`（759 KB，签名版）。
   配套工具 `bkerler/edl`、`qdl`、`strongtz/edl-ng` 都是自由软件。
3. **进入 EDL（9008）必须动硬件**，软件进不去。实测：
   - `adb shell su -c 'reboot edl'` → 只是普通重启回 Android；
   - 往 `misc` 的 BCB 命令位写 `boot-into-edl` → 也是普通重启（`bootonce-bootloader` 才进 Download）；
   - S23 系列进 9008 要靠**主板测试点短接**或 **EDL 线（USB 上 300kΩ 左右短 D+/ID 到 GND）**，
     也就是要开背盖。

**EDL 能带来什么**：它绕开 ABL 的 KG 内容闸门，直接读写分区 —— 刷 patched `init_boot`、
dump 任意分区、随时救砖（我们已经砖过两次），不受 `-5` 和 Download 会话限制。
**限制**：开机的 AVB 校验仍在（vbmeta 仍需 OEM 签名），所以单靠 EDL 写 patch 镜像可能仍起不来；
但有了 EDL，可以自由改 `param`/`persist`/`misc` 反复实验，不必每次冒 Download 失败的风险。

## 25. 找到同代 S24 的完整审计仓库，与我们的结论互相印证

`keyarr/oems24-audit`（SM-S928B，One UI 8.5 `S928BXXU5DZDP`，只读取证）把这条链完整逆过一遍，
结论和我们高度一致，并补上了我们没走到的部分：

- One UI 8 起官方**删掉了用户侧 OEM 解锁入口**，命令行走 `androidboot.other.locked=1`；
  但 ABL 的解锁机制本身还在。
- `devinfo` 布局：magic `SAMANDR-BOOT!` @0，`+0x0d = IsUnlocked`，`+0x0e`、`+0x90`、`+0xc88` 其它字段；
  `IsUnlocked` 只有一个写入者 `SetUnlocked`，由 **`GetEMBit(3)`** 驱动；AVB 的
  `read_is_device_unlocked` 会读它并真正跳过校验。
- **EM 状态不在任何普通分区**：TA 用 `qsee_stor_*` + AES-GCM 存在安全存储的 `engmode` 区（RPMB），
  所以 `/steady`、文件系统里的 blob 都替代不了。
- Token 由三星 RSA 锚签名、与设备+请求绑定，MODE 在签名体内，本地改不了。
- 他们同样认为没有本地路径能凭空造出 unlock 状态，剩余开放项是 Odin 每条 USB 命令的
  "先解析后校验" 审计、`steady`/`misc` 解析器完整环路。

**我们这轮的实测补充**：把 `devinfo+0x0d` 直接写成 `0x01`（备份在 `/data/local/tmp/devinfo.bak`）。

- 该字节**跨一次重启保留住了**（没被覆盖，这点比他们的悲观说法宽松）；
- 但 `verifiedbootstate` 仍是 `green`、`flash.locked` 仍 `1`，刷 patched `init_boot` **仍然 `-5`**。

所以 `devinfo` 单独写确实只是"状态标着解锁"，既没让 AVB 放行，也没过 KG 内容闸门；
真正的开关还是 EM 位（他们的 bit3 / 我们闸门里的 bit0）与 KG 状态。

**EM token 的历史公开材料**（不保证现在还发）：GSMHosting 帖子里有人贴过含 mode
`3_4_5_10_21_28` 的 ESS 命令与 token 流程。要往下走，只能去拿 token。

## 26. EM token 的路怎么走：设备上确实有完整 EM 栈

顺着审计仓库的结论继续查设备侧：

- `/vendor/etc/vintf/manifest/engmode_manifest.xml` 声明了 HIDL HAL
  `vendor.samsung.hardware.security.engmode@1.0::ISehEngmode`（`lshal` 里是活的）；
- HAL 方法（从 `vendor.samsung.hardware.security.engmode@1.0.so` 提取）包含
  `getStatus`、`getModesbit`、`getNumOfModes`、`installToken`、`isTokenInstalled`、
  `getRequestMsg`、`makeTokenReq`、`commandForEss`、`recoveryItl`、`removeToken` 等；
- `/vendor/bin/emservice` 是它的 binder 服务端（`libengmode_server.so:engmode_binder_server`），
  而 `libengmode_server.so` 依赖 **RILD**（`OpenClient_RILD` / `InvokeOemRequestHookRaw`）——
  说明 ESS 请求是走 **RIL OEM 原始 AT 命令** 发出去的，和 GSMHosting 那套 DASEUL/ESS 流程一致；
- TA 侧（`em.img`，`keyarr` 审计）对 DID 前缀 `30` 是硬编码 RSA 锚，并强制 DID/机型/nonce/有效期校验，
  MODE 段在签名体内。**我们的 DID 是 `2004376D249F2911`（前缀 20、结尾 11=量产）**，锚点可能还不同。

结论：本地装 token 的通道齐全（HAL/emservice 都在），真正缺的是**用我们的 DID 向 ESS 要一份含 mode 的 token**。

补充实测：写了个 `scripts/emcli.cpp`（NDK 编译，dlopen `libengmode_client.so`）想直接调 EM 客户端，
已摸清对象布局（ctor 会 memset 0x11000，需要 ≥0x12000 字节缓冲并把 `gEngmodeclient` 指过去）和
必须显式 `getServer()`；但卡在 binder 域：`emservice` 在 **/dev/vndbinder**，
客户端 ctor 却先把 `ProcessState` 绑到 **/dev/binder**，之后再 `initWithDriver` 会拒绝；
放在 ctor 之前 initialize 又会在 `ProcessState::init` 写只读页崩溃。
目前 `mServer` 仍是 0，方法一调就 SIGSEGV。`lshal` 查这个 HAL 也要 root（shell 域被 SELinux 拒 `find`）。

换到 **Java `android.os.HwBinder`（hwbinder/HIDL）**这条：`getService` 成功拿到 binder，
并从 `Bp` 侧反出了 code（3=isTokenInstalled、4=removeToken、5=getNumOfModes、6=sendFuseCmd、
7=getVersion、17=getTuc）；但所有 transact **发出去都不返回**（`lshal debug` 对同一服务是秒回），
一开始怀疑是缺 `SehCallerInfo` 字段；但连 `android.hidl.manager@1.2::IServiceManager` 的必答方法
也一样挂（`lshal debug` 同服务秒回），所以是**传输上下文**问题：`app_process` 已把 binder 绑到
`/dev/binder`，Java `HwBinder` 的 `hardware::ProcessState` 被污染，handle 失效。
`Looper.prepareMainLooper()` 无效。工具见 `scripts/helpers/Em.java`。
历史上这需要 ESS 账号/工具，现在是否对零售机开放未知。

负面影响：`devinfo+0x0d` 现在是 `1`（我们写进去的，跨重启保留、无副作用），
`verifiedbootstate` 仍然 `green`、刷机仍 `-5`。备份在 `/data/local/tmp/devinfo.bak`。

### 突破：直连 EM TA 已经通了

改写思路直接调 `libengmode_server.so` 的 `EngineeringModeWorld::*`（底层走
`libengmode_tlc.so` → `QSEECom` → `engmode` TA），绕开 binder 与 RILD。两个硬前置：

1. 必须 `setgid/setuid(1000)`——`libstork_shared` 的 steady 读写只在 uid==euid==1000 才正常工作；
2. **进程名必须是 `emservice`**——stork 的 `STORK_BIRD` 按进程名放行，否则 `Permission error!`。

满足后 `emInit()` 返回 0、TA 被 QSEECom 正常加载并应答。`emGetModesBit`/`emIsTokenInstalled`
当前返回 TA 状态字 **0xf02d0010**（与审计仓库记录的状态字一致），说明还缺前置步骤
（时间同步 / 先装 token）。工具：`scripts/emworld.cpp`。

**再深一层（同样结论）**：`emInit()` 本身是 TA 命令 **25（EM_CMD_INIT）**，
它先把 `steady` 分区 **idx 3（11264 字节）** 的初始化块读进 payload 再下发。
本机 `steady` 4 MB 里只有 650 个非零字节（几乎全空），TA 拿到全零的 init 块 → 返回 `0xf02d0010`，
后面 `emIsTokenInstalled`/`emGetModesBit` 连带失败。

也就是说 **EM 这条路要先把 steady 的 init 块建立起来**，而那玩意正常是靠一次成功的 ESS 同步生成的。
停掉 `emservice` 再跑也同样失败，可以排除"TA 被占用"。
（顺手记：本机 steady 已备份 `/data/local/tmp/steady.bak`，sha256 `e6ce942b…`。）

### 下一步计划（两条并行记录，先 ①后 ②）

- **① ESS 交换**：`EngineeringModeWorld::emEssCommand(int, u8* req, u8* rsp, u32* rspLen)`。
  目标是把 EM 的 ESS 会话跑起来，让 TA 生成 steady init 块（甚至直接下发 token）。
- **② 时间同步**：`emGetTimeRequest(u8*, u32*)` → 自己签/回灌 → `emVerifyTime(u8*, u32, u8*, u32*)`。
  先把 `EM_CMD_TIME_CHECK` 走通，再回头试 `emInit` / `emGetModesBit`。

任意一条通了，都回到 `emInit → emIsTokenInstalled → emGetModesBit` 复验。
hard-fail 判据：TA 仍返 `0xf02d0010`（init 块缺失）或 `0xd01f0012`。

**两条路都试过，结果记在这：**

- **① ESS 交换**：`emEssCommand(int cmd, u8* req, u8* rsp, u32* rspLen)`。它内部先 `preparePayload(12,1)`
  再下发；用 `cmd=0` + 空 req 调用会**卡住不返回**（>40s），说明它在等 CP/ESS 回包。
- **② 时间同步**：`emGetTimeRequest(u8*, u32*)` 同样**直接卡死**（>40s），
  甚至在 `emInit` 之前也一样。日志里没有任何 TA 应答，只在等待。
- 唯一**能返回 0** 的接口是 `emGetLastTokenStatus(u8*)`，但输出字节是 `0x44`（`'D'`），
  结合 `emInit` 的 `0xf02d0010`，基本可以认定：**本机的 EM 会话从未建立，时间/ESS 都拿不到**。

**补充线索**：`gsm.sim.state = LOADED,ABSENT`、`gsm.operator.alpha` 为空 —— SIM 卡在但**没有运营商服务**。
ESS 请求正是走 CP（modem 的 OEM AT 通道），没有蜂窝数据就永远等不到回包，这正好解释了上面两个接口为什么会阻塞。

结论：在没有任何 ESS 侧凭据的情况下，EM TA 这条线停在「init 块为空 + 时间请求阻塞」。
要再往下必须有 ESS 侧的东西（订阅/账号/工具），否则只能等 CP 侧（modem）先有响应。

### 当前双线计划（都记着，一条不行走另一条）

- **A. ESS/EM 线**：需要①SIM 有运营商服务（现在 `LOADED,ABSENT`）②ESS 侧凭据。
  有服务后重跑 `scripts/emtime.cpp`（`emGetTimeRequest`）看是否还阻塞；通了再 `emEssCommand` → token。
- **B. KG 线**：闸门表允许状态 **1(Checking)** 和 **4**。已确认 `Active(2)` 不放行。
  目标：让 TZ 进入 1 或 4。手段仍是 `KnoxGuardManager.setCheckingState()`（此前恒 `-1`，要看是否与 HAL 状态有关）
  或 enroll 到租户（需要能过 TZ 的 certs）。

### 往 steady 里塞块是有效的（可作注入点）

steady 的分区布局是「表驱动」：`emsrv.so` 里 idx→(size,offset) 两张表在 `0x7538`/`0x7554`，
idx3 对应 **offset 0x2400，长度 0x2c00**（11264）。直接把这块改成已知内容并回写，
TA 的行为立刻变化：原来后续接口一律 `0xf02d0010`，写入非零内容后变成 **`0xf0780010`** ——
说明 TA 真的读这块，且 ESP 注入可行。

顺带在 TA 的字符串表里发现 token 段 magic 是 **`INTE`**（旁边就是 `MODE`/`VALI`），
`em_crypto_verify_recovery_data` 等也在附近。把 `INTE` 写到块首后错误类型没再变，
所以 init 块的判别在别处，还没找到。

### 继续逆 TA：INITE 校验找到了，但 init 块不是它

在 TA 里定位到 `cmp w8, #0x544e49` + `movk #0x4554`（即 `INTE`）后 `b.ne <magic error>` 的代码（`0xe3a0` 一带），
确认这是 **token 的 INTE 段解析**：随后按 `%02x/%02x/%02x/%02x` 打印实际 4 字节并报
`magic error`，再按 offset/长度字段逐段解。

但把 `INTE` 写到 steady idx3 块首，`emInit` 仍返回 `0xf02d0010` —— 说明 **init 块不是 INTE 段**，
它自己的判别还没找到。另一个线索：`emInit` 在 `cmp [ctx+8], #0x19` 后走的是 `em_lite_entry`，
即命令 25 在本机被路由到 **lite 后端**，这条支线的解析流程和 token 段不同。

### lite 后端（libengmode2lite.so）的段 magic 全挖出来了

`em_lite_entry` → `em_context_make_request` → `em_cmd_handler`，整条是**한 HLOS 软件实现**，
按段解析那个 11264 字节块。反汇编里直接能读到各段 magic（`mov`+`movk` 组成 4 字节）：

| magic | 位置 | 含义 |
| --- | --- | --- |
| `TOKE` | 0xeaac（`em_token_is_installed`） | token 头 |
| `DEVI` | 0xef24 | device info |
| `ISSU` | 0xf3b8 | issuer info |
| `VALI` | 0xfc74 | validity info |
| `GRDB` | 0x101c4 | ？ |
| `MODB` | 0x102fc | mode db |
| `INTE` | 0x128b8 | integrity |
| `NNTC` | 0xbef4（`em_client_verify`） | ？ |

对应错误码也在同一函数里：`0xf02d0010`(16)、`0xf02d0011`(17)、`0xf02d0013`(19) 都是
`em_token_is_installed` 的分支，`0xf050…` 出自 `em_token_get_priority_time`。

**实测把块首写成 `TOKE` 后 `emInit` 仍是 `0xf02d0010`** —— 说明 init 用的不是这个 token 结构
（或还需要更多段/长度字段才会推进）。至少现在有了完整的段格式表，可以按它去拼一个假 token。

### TA 侧的结构线索（也记下）

TA 里同样有 magic 常量表：`NNTC`(0xd14)、`TOKE`(0x9a84)、`DEVI`、`ISSU`、`VALI`、`MODB`、`GRDB`、`INTE`(0xe398)、
`CORE`(多处)、`ENGT`、`ENGI`。其中 0xd14 附近是一段**记录遍历**：
步长 `0x108`，每条的 magic 在 `+0x100`，命中 `NNTC` 或经 `0x8c68` 判定通过才继续，否则打
`magic error`。

**试过把 `NNTC` 写到块内 `+0x100`、把 `TOKE`/`NNTC` 写在块首，`emInit` 仍返回 `0xf02d0010`**
（这个码出自 `em_token_get_token_id`），所以更可能的情况是：**init 必须要有一个已存在的 token**，
而装 token 又要先 init —— 鸡生蛋。下一步应该直接 `emTokenInstall` 一个手工 token
（工具 `/data/local/tmp/eminst`），按 TA 的 `0x108` 记录格式填，一段段把错误往前推。

### 找到 init 块的真实格式（借 S24 样本），但结论是「需要 token」

`keyarr/oems24-audit` 的 `steady.bin` 里 idx3 区域是**非空的**（他们机器虽然也锁着，但至少跑过 EM），
直接能看到结构：偏移 0x2420 起是 ASCII **`ESI`**，随后是 TLV（u16 type + u16 len），
`0x2434` 就是 **DID 字符串**（16 字节，S24 的 `3004484185377A11`），后面还有 `11:10`、`03:10`、
`0a:de00` 等条目；块首 0x20 字节像哈希。

把这块整体搬进本机 steady idx3 后：
- `emInit` 仍 `0xf02d0010`（不变）
- 但其它接口的 TA 码从 `0xf02d0010`/`0xf0780010` 变成 **`0xf00b0010`** —— 结构确实被认了

**踩坑补充**：`eminst` 也必须把进程名改成 `emservice`，否则 steady 读失败、直接返回 `0xd0010063`，
根本走不到安装逻辑；改对名字后同样的假 token 会真正进解析器，返回 `0xf02d0010`（token id 阶段）。

**关键判定**：steady 的 idx 表里 **idx1 = offset 0x5000、长度 0x11000，就是 token 区**，
而两块机器的 idx1 都是**全零**（谁都没真正 enroll 成功过）。所以 `emInit` 卡的是"没有 token"，
ESI 块只是附属数据。这也解释了为什么换任何块内容 `emInit` 都是同一个码。

→ EM 这条路要真正走通，**必须要一份签名 token**；否则只能到"结构被认、init 不过"为止。

### 又试了两把，仍然停在 0xf02d0010

- 用 `TOKE` + 全零 11264 字节当 token 灌入 → `0xf02d0010`
- 用 S24 的 ESI 块（`d5 29 82 f6 …`，0x2420 处才是 `ESI` 那 10 字节头）当 token 灌入 → 同样 `0xf02d0010`

在 TA 的 `0x96ac` 附近能看到 token 头校验是**对 `ctx+0x50a` 的 10 字节 memcmp**，
而 `esi` 块里 `45 53 49 1e 00 45 00 00 00 00` 正好 10 字节 —— 头结构对上了，但还缺后面的段/签名。

**最终判断（这轮可以定论）**：EM 路线要做到 `install rc=0`，必须有一份**真 token**；
本地只能把通道、注入点、格式准备到这一步。工具与 runbook 都已备好，缺的就是 token 这个外部输入。

## 27. 阶段定论（2026-11-14）

本地自足路径已耗尽。EM 通道、steady 注入、段格式、token 灌入通道全部打通，
但 `emInit`/`emTokenInstall` 都需要一份**三星签名的 token**；KG 侧则需要租户登记或能过 TZ 的真证书。
两条都是外部输入。详见 `docs/summary.md` 的「三条路」。

## 28. 用 root 直接 dd 写 `init_boot`：绕过了 Odin 的 KG 检查，但被开机 AVB 拒

有 root 后想到一层还没试过的：`-5` 是 **Odin 会话**里的 KG 内容校验，那就不走 Odin，直接 dd 分区。

- 备份原厂：`/data/local/tmp/init_boot.stock`（sha256 `72201800…`，与固件里的 `init_boot.img` 一致）
- `dd if=init_boot.ksu.img of=/dev/block/by-name/init_boot` → 写完回读 sha256 与源完全一致
- `adb reboot` → **开机卡在 Security Error「已被锁定」界面**，USB 不枚举、进不了系统

结论分两层，很清楚：

1. **KG 检查确实只在 Odin 会话里**，dd 能物理写进去（内容校验没拦住我们）；
2. 但**开机时的 AVB/签名校验是另一道门**：bootloader 还是 locked + green，改过的 `init_boot`
   与未改的 `vbmeta` 摘要对不上 → 直接 Security Error。

所以「临时 root 变永久」要过的是**两道**门，dd 只买到第一道的门票。恢复方式：进 Download 模式，
`heimdall flash --INIT_BOOT /tmp/fwimg/init_boot.img`（分区名是全大写 `INIT_BOOT`，写成小写会被 PIT 拒），
刷原厂内容在 KG `Active` 下是放行的，刷完正常开机、再重跑 `temp_root.py` 即可恢复 root。

## 29. 开机默认 USB 模式：不是 `persist.sys.usb.config`，是 Secure 设置 `default_usb_configuration`

想让机器开机自动进「文件传输 + adb」而不是仅充电。先按常规 `setprop persist.sys.usb.config mtp,adb`：
**重启后被覆盖回 `sec_charging,adb`**（persist 值也被改写），不可用。

在 `SecSettings.apk` 里找到 `DefaultUsbConfigurationPreferenceController` 与
`usb_configuration_values`（`none/mtp/ptp/rndis/midi/audio_source`），定位到真正开关是
`Settings.Secure.default_usb_configuration`。设 `mtp` 后**连续两次重启**都稳定起在 `mtp,adb`。
`persist.sys.usb.config` 保持 `sec_charging,adb` 属正常（它记录"上一次实际状态"，不是默认值）。

## 30. token 解析函数读到了细节，但仍不前进

反编 TA 里 `0x9658` 起的那个函数（首个参数作 token 缓冲，第二、三个作输出）：

- `0x96c4` 先 `memcpy(buf, ctx+0x50a, 10)`；
- 随后 `0x96d8` 拿 `buf[0..3]` 与常量 `3f e4 e4`（VA 0xf43de）比较，**不等就返回 `0xf02d0010`** 并置 ctx 位。

于是试了这些 token 前缀，全部仍是 `0xf02d0010`：
`TOKE`、`NNTC`、ESI 块的 10 字节头（`4553491e004500000000`）、S24 整块、全零、`3f e4 e4`。

说明这个函数是**令牌状态检查**（用 `ctx+0x50a` 覆盖前 10 字节），`emTokenInstall` 卡在它之前/别处，
`0xf02d0010` 在 TA 里被多条分支共用，不能只按错误码判定走到了哪一步。

注意：`EM_CMD_INSTALL_TOKEN` 字符串在 0xf3926，但它落在 rodata 段、反汇编只出 `<unknown>`，
按 adrp/add 组合找不到引用，需要先按段重建映像再做 xref。
