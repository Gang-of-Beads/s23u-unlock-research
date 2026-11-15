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

## 31. 有网以后：EM 不再阻塞，但会更快地撞回同一个码；token 请求接口也是死循环

联网（Wi-Fi 192.168.1.231）后重跑 `emGetTimeRequest`：**不再卡死**，秒回 `0xf02d0010`
（之前 >40 s 的阻塞确实是网络）。所以 ESS 的阻塞是网络问题，不是通道本身。

`gsm.network.type` 变成 `IWLAN,Unknown`（modem 走 Wi-Fi 呼叫注册），SIM 的 WWAN 依旧 `OUT_OF_SERVICE`。

新挖到的接口：`EngineeringModeWorld::emGetTokenRequest(const u8*,×5, u8*, u32*)`
（符号 `_ZN20EngineeringModeWorld17emGetTokenRequestEPKhS1_S1_S1_S1_S1_PhPj`），工具写在 `scripts/emtreq.cpp`。
调用返回 **`0xd04e0015`**（HLOS 侧码），换参数内容、长度都不变 —— 因为 **`emInit` 失败**它就直接退。

于是出现死循环：`emInit` 说"没 token"，`emGetTokenRequest`（本该去要 token）说"init 没成功"。

再说 ESI 块：把 S24 样张里 0x34 的 16 字节 DID 换成我们的 `2004376D249F2911` 写回 steady，
`emInit` 仍是 `0xf00b0010` —— 说明块首 0x20 字节（疑似哈希/加密）和后面的 `2525671334000AEF` 类字段
没对上，TA 在解析内容前就拒了。

## 32. KG HAL：TZ 会话终于能建起来（重启后 ctx 为 NULL 的解法）

以前每次调 KG HAL 都是 `TACtx is NULL` → 返回 -1000 → 客户端被 SIGKILL。这次找到真正原因：
**ctx 是懒创建的，由一个特定方法触发 `KGTA_Initialize`**（日志：`initializing kgta context...` →
`lookupTA(tz_kg)` → `KGTA_Initialize`），不是由开机流程建。

实测触发方法 = **code 12**（`setClientData` 形状：`int` + `byte[]`，32 字节即可）：

```bash
su -c 'setprop ctl.stop kgtaserv; sleep 1; setprop ctl.start kgtaserv; sleep 3'
su -c 'CLASSPATH=/data/local/tmp/kgcall.jar app_process /system/bin dev.pi.kgcall.Main 12 int:0 ba:32'
su -c 'CLASSPATH=/data/local/tmp/kgcall.jar app_process /system/bin dev.pi.kgcall.Main 7 int:0'
```

- code 12 返回成功（`00000000`），随后 **code 7（getKgState）返回 `2`**，与 prop `knox.kg.state=Active` 一致
  —— KG TA 会话第一次真的通了；
- 但会话**很脆**：任何参数形状不对的调用都会把 `kgtaserv` 打死（`/vendor/bin/hw/vendor.samsung.hardware.tlc.kg-service`
  是 `oneshot`，死后 init 状态仍显示 `running`，必须 `ctl.stop` + `ctl.start` 才能再拉起）。
- 重新拉起后 ctx 又是 NULL，要再走一次 code 12。

### 状态相关方法的结果

| code | 方法 | 结果 |
| --- | --- | --- |
| 7 | `getKgState` | 成功，恒 `2`（Active） |
| 5 | `getClientData` | 成功，返回 36 字节（status+0x18+全零缓冲区） |
| 12 | `setClientData` | 首次调用建 ctx；ctx 已存在时再调会被 SIGKILL（形状/时机敏感） |
| 17 | `setUserCheckingState` | **TZ 稳定回错误码 `262`（0x106）**，改不了状态 |
| 19 | `unlockScreen` | HAL 回 `error code:0`（TZ 接受），但状态仍是 2、prop 仍 `Active` |
| 20–26 | `verify*` / `resetKgInfo` / `getTAInfo` / `provisionCert` | 参数形状不对即 SIGKILL，尚未定形 |
| 18 | void 方法 | 成功返回 |

结论没变：**`unlockScreen` 在 TZ 里是空的，`setUserCheckingState` 被 262 拒**，所以还是要 KG 服务器侧
（登记/放行）或 EM token。但这次至少把「客户端触发」这条路彻底打通到 TZ 边界了，以前只能看到 -1000。

工具源码与 jar 已收进仓库：`scripts/helpers/kgcall/`（`src/dev/pi/kgcall/Main.java` + `kgcall.jar`）。

## 33. KG HAL 全体方法表（`kgndk.so` 有符号，含 `initiate`/`terminate`）

`/vendor/lib64/vendor.samsung.hardware.tlc.kg-V2-ndk.so` 的 dynsym **没被 strip**，
`llvm-nm -D` 能直接列出全部 AIDL 方法（这比之前靠 vtable 槽位猜准确得多）。
逐个 code 用 `int:0 + 3×byte[32]` 满参调用并抓 HAL 日志里的方法名，得到 code→方法：

| code | 方法 | TZ 错误码 |
| --- | --- | --- |
| 1 | generateHotpDhRequest | 520 |
| 2 | getClientData | 0 |
| 3 | getHdmStatus | 261 |
| 4 | getHotpChallengeCode | 0 |
| 5 | getKgId | 0 |
| 6 | getKgPolicy | 520 |
| **7** | **getKgState** | **0**（恒 `2`） |
| 8 | getLockActionData | 520 |
| 9 | getLockActionId | 0 |
| 10 | getNonce | 2305 |
| 11 | getTAInfo | 4101 |
| 13 | lockScreen | 0 |
| 14 | provisionCert | 264 |
| **15** | **resetKgInfo** | **0（但状态不变，仍 2）** |
| 16 | setClientData | 0 |
| **17** | **setUserCheckingState** | **262** |
| 19 | unlockScreen | 0（状态不变） |
| 20 | verifyCompleteToken | 264 |
| 21 | verifyHotpDhChallengeCode | 264 |
| 22 | verifyHotpPin | 0 |
| 23 | verifyHotpSecret | 0 |
| 24 | verifyKgPolicy | 264 |
| 25 | verifyKgRot | 0 |
| 26 | verifyRegistrationInfo | 264 |
| 27 | verifySfPolicy | 261 |
| 28 | readSfPolicy | 261 |

参数形状（从 onTransact 的反汇编读出来，不是猜）：1/2/3/5/6/7/8/9 收 `int`，4/10/12/13/15/16/17/18/19/20/21/22/23/24/25/26/27/28 收 `byte[]`（部分收 2–4 个），
`initiate`/`terminate` 不收参（对应 code 12/18，实测 code 12 才会建 ctx，与 `initiate` 语义一致）。

**关键结论**：`resetKgInfo`、`unlockScreen`、`lockScreen`、`verifyHotpPin`、`verifyHotpSecret` 都能返回 0，
但 **KG 状态一律不动**；`setUserCheckingState` 恒 262；要动状态必须喂**真数据**给
`verifyRegistrationInfo`(26) / `verifyKgPolicy`(24) / `provisionCert`(14)，这三个现在都回 264（数据无效）。

## 34. ESI 块首 0x20 字节确实被校验

把 S24 样张块首 0x20 字节清零、其余（合法 item 表）保持不动后写入 steady：
`emInit` 从 `0xf00b0010` 退回 **`0xf02d0010`** —— 说明这 0x20 字节是 ESI 的**头/签名**，
不通过的话 TA 连 item 表都不看。下一步要么解出它的算法（疑似 AES/hash，需 TA 内密钥），
要么从真实设备上抓一份同型号的 steady 块来对照。

## 35. `getTAInfo` 的形状与返回值（TA 内的设备身份绑定被证实）

code 11 (`getTAInfo`) 的形状是 **`int` + `byte[]`**（只给 `int` 会被 SIGKILL——HAL 对空回复会打死客户端）。
补一个 `byte[]` 后正常应答（字符串长度前缀 + 内容）：

| index | 返回 |
| --- | --- |
| 1 | `2` |
| 2 | `false`（= `CertProvisioned` 为假，与此前 framework 侧读数一致） |
| 3 | `2` |
| 4 | 32 字节 **`AAAA000000000000000004376D249F29…`** —— 前缀固定，后半段含我们 DID 的片段（`4376D249F29…`），即设备绑定标识 |
| 0, 5–8 | 仍 SIGKILL（形状或前提不同） |

说明 TA 里确实存了本机的绑定种子，所以「随便造数据」注定过不了校验。

## 36. ESI 头算法的方向：HMAC

TA 里有一整套 crypto helper 字符串：`em_crypto_hmac`、`em_crypto_sha256`、
`em_crypto_aes_256_gcm_encrypt/decrypt`、`em_crypto_aes_256_ctr_*`，以及
`EmgineeringMode20 AES256 … Label/Context, MSTG` 这类 key 标签。
结合审计仓库"EM 状态在 RPMB `engmode`，走 `qsee_stor_*` + AES-GCM"的结论，块首 0x20 字节最可能是
**用 TA 内部密钥（可能由 DID/efuse 派生）对整块算的 HMAC**，而不是可自算的简单 hash
——这解释了为什么换了 DID、清了头都过不去，也解释了为什么必须真 token。

要继续攻这条，只能：① 在 TA 里定位 `em_crypto_hmac` 的调用点与 key 来源（key 大概率在 efuse/TZ，仍需真 token 才能闭环）；
② 搞到一台同型号真机的 steady 块做对照（能直接验证"头是否设备相关"）。

## 37. 三个对照实验：ESI 头是被校验的完整性字段，item 只做交叉校验

| 实验 | 结果 |
| --- | --- |
| 清块首 8 / 16 / 24 / 32 字节 | 全部 `0xf02d0010`（清 8 字节就够失败，说明开头几个字节就被校验） |
| 保留块首 0x20、其余 item 全清零 | `0xf02d0010`（没有 item 也不行） |
| **只翻块首第 3 个字节（item 完全不动）** | **`0xf02d0010`** |
| 改 item 里的 DID（块首不动） | `0xf00b0010` |

结论：
- 块首 0x20 字节是**完整性字段**（MAC/hash），一个 bit 都不能动；动了它 TA 直接判 ESI 无效（`0xf02d0010`）；
- item 内容**不是**逐字节被 MAC 保护（改 DID 只到 `0xf00b0010`），DID 是另外做交叉校验；
- 所以本地伪造 ESI 必须能重算这个头 —— 而 TA 里唯一会自己重写 ESI 的入口是 `emTokenInstall`/ESI update，
  **又绕回「需要真 token」**。两条分支在这一点上合流。

实验后已把 `myblk.bin`（含本机 DID 的 S24 样张）写回 steady。

## 38. 暴力破解 token 到底要多久（实测速率 + 估算）

先把「破解」拆清楚，因为 token 有四种不同性质的东西，代价差天文量级。

**实测速率**（本机、单进程循环、只做 `emTokenInstall`）：一次 TA 往返 **约 218 ms**
（50 次 10.9 s）。即约 4.6 次/秒、1.6 万次/小时、40 万次/天。走 `adb shell` 每次调用是 513 ms，
所以批量跑必须写在进程内，不能一遍一遍起进程。

| 目标 | 需尝试次数 | 需要多久 |
| --- | --- | --- |
| 已知前缀后的 1 字节（8 bit） | 256 | 约 1 分钟 |
| 2 字节字段（16 bit） | 6.5 万 | 约 4 小时 |
| 3 字节（24 bit） | 1670 万 | 约 42 天 |
| 4 字节（32 bit） | 43 亿 | **约 30 年** |
| RSA 签名（2048/4096） | 2^2048 | 不可穷举 |

**所以结论是：**

1. **签名永远不可能被暴力破**。只能让 TA 自己认，或者拿到真签名。
2. **结构可以暴力摸，但必须是"小字段"**。现在已知 token 头是三字节 `3f e4 e4`（已拿到，不用爆），
   且 `ctx+0x50a` 那 10 字节是复制进来的、不参与比较。
3. 真正的拦路虎是 **INTE 段**：TA 里 `em_crypto_hmac` / `em_crypto_sha256` 都在，`INTE` 语义是完整性。
   如果它只是**普通 SHA-256**（可本地算），那结构摸通后能推进到最后一步的签名校验；
   如果是 **HMAC（TA 内密钥）**，那么每次改结构都得靠 TA 的 2 bit 错误码（`0xf02d0010..0x13`）当梯度，
   搜空间立刻变成 2^N 级别 —— 此时**结构暴力也基本没戏**。
4. 现实路线因此是：**先确定 INTE 是 hash 还是 HMAC**（静态读 `em_client_verify`/`0x128b8` 附近的 INTE 处理，
   看是否调用 `em_crypto_hmac`），再决定要不要投入暴力搜索。

一句话："暴力破解 token" 不是 2^N 的力气活，真正的成本在于**摸清格式**；而只要 INTE 是 HMAC，
格式摸清了也造不出可用的 token。

## 39. INTE 段的性质：是签名，不是可自算的 hash

顺着 `INTE` 常量（0xe398）读下去，它是**段解析器**，把这个段拆成两个子项分别拷进上下文：

- 子类型 **1**：长度上限 **`0x201`（512 字节）**，落到 `ctx+0x2`；
- 子类型 **2**：长度上限 **`0x1000`（4096 字节）**，落到 `ctx+0x204`；
- 之后在 0xbcd4/0xbd50 一带拿它和上下文里的长度/16 字节值做比较，再调 0xc9cc 走校验。

`0x201` 这个上限基本坐实了子项 1 是**签名**（512 = RSA-4096 的模长），子项 2 是**被签的内容**。
也就是说 `INTE` 不是"对内容算个 sha256 就行"的字段，而是**厂家 RSA 签名**。

**这直接判了暴力破解的死刑**：

- 哪怕把结构全部摸对、把 INTE 塞成随便 512 字节，TA 也只会在签名校验处失败；
- 签名不可伪造 → **摸清格式也拿不到可用 token**；
- 唯一能让 TA 认的，还是三星签出来的真 token。

附带的坏消息：连结构现在都还没过第一关（任何改动都停在 `0xf02d0010`），所以连"摸到签名校验那一步"都需要先解决块首完整性字段。

## 40. 外部资料命中：token 格式被公开（`CamsShaft/arbitrary-R-W-...`）

网络检索（DDG via r.jina.ai）找到 XDA 帖 4797708 与仓库
`CamsShaft/arbitrary-R-W-for-steady-and-param-partitions`（2026-08 发布，作者 peedsllaBoG）：

- 他用 `frigate` socket（Android 15 起被悄悄改名 `knox_native`，SELinux 规则没跟上，成了孤儿）
  在 **uid 1000** 下读写 `steady`/`param` —— 我们已有 root + QSEECom，这条不如现成手段，但可当旁路；
- **仓库里带 `engmode.py`，把 token 格式写全了**：
  - 前缀 `ENGRSS0002`（"Format B"），随后 `headerLen(4)` + **8 个段偏移**；
  - 段结构 = `magic(4) + size(4) + count(4) + TLV`，段为 `TOKE/DEVI/ISSU/MODE/VALI/MODB/GRDB/INTE`；
  - `INTE` = 段内 tag1 是 **256 字节 PKCS#1 v1.5 SHA-256 签名**、tag2 是 `设备证书 + 根证书` 串接；
  - 签名覆盖 **header + 除 INTE 外的所有段**；作者明确说需要"泄露的 rootCA 私钥"才能真正解锁。

已把脚本收进 `scripts/emtools/engmode.py`，并按本机改了 `did=2004376D249F2911`、`model_name=SM-S918B`。

### 用它实测：错误码第一次从 `0xf02d0010` 往前走了

自签 RSA-2048 设备证书 + 自签根证书生成 token 后灌入：

| 版本 | 结果 |
| --- | --- |
| 原脚本（header 偏移顺序 toke,devi,issu,mode,vali,**inte,modb,grdb**） | `0xf0100015` = **"offset isn't normal"** |
| 把 header 偏移改成**升序**（…vali,modb,grdb,inte） | `0xf02b0010`（更深一层） |

补丁长度（4096/8192/16384/69632）都不影响。说明：**格式解析已被走到**，但 header 偏移必须严格升序，
现在卡在下一层（`0xf02b` 家族来自按类型查表，`+index`）。

### 另外拿到的 TA 字符串（说明校验强度）

`em_crypto_verify_cert`、`Cert len isn't normal`、`root_ca_type : %d`、`Failed to read root CA pubkey`、
`Failed to X509_verify`、`Unexpected sig size`、`Unexpected server cert size`、`Unknow type(0x%04x)`。
即 TA 内**确有根 CA 公钥**并做完整 X509 链验证 —— 所以自签链大概率过不了最后一关，
真正需要的是**能对上内置根公钥的证书链**（找泄露的 rootCA 私钥才有戏）。

## 41. 「降到 One UI 7 找回 OEM Unlock」——按固件清单判定：不可行

用公开固件库（SamFrew XSG 列表）核对了本机型号全部可达构建，二进制位与 UI 版本是对应的：

| 二进制 | 构建（XSG） | 对应大版本 |
| --- | --- | --- |
| **9** | `S918BXXS9EZB/9EZC`、`S918BXXU9FZD` | One UI 7（E 段）/ One UI 8 早期（F 段） |
| **A（=10）** | `S918BXXSAFZE … AFZI`、`S918BXXUAGZI` | One UI 8/8.5/9 |

本机 `ro.boot.rp=10`、当前 `AFZH3` 属 A。**One UI 7 最高只到二进制 9，全部低于 10**，
所以 ARB 直接拒 —— 连"只刷 AP"也救不了（AP 同样是二进制 9 签的）。这条与第 19 条一致，
现在有清单级证据了。

推论：One UI 7 有没 OEM 解锁开关已经无所谓，**够不着**。要拿回解锁只能：
① 让 KG 进 1/4（服务器侧）；② 弄到真 EM token（见 §40 的格式与 §42 的证书要求）。

## 42. 证书锚点到底长什么样（来自 S24 同代审计，与本地 TA 字符串一致）

`keyarr/oems24-audit` 的 `root-to-boot-exploit-surface-analysis.txt` 把 TA 解析器写得很细，关键点：

- INTE 的 tag2 是**叶子证书**（不是"设备证书+根证书串接"），根是**内置在 TA 里**的：
  "两对 0x126 字节 SHA-256 pin 的 X.509 SPKI"，另外还认 `0xf4df0`/`0xf503c` 两个老 ENGRSS0002 槽位；
- 校验分支：`keyUsage` 带 0xC0 之外的位 → 走特例，比较整段 DER 的 SHA-256 与硬编码摘要；
  否则**必须有 subject CN == `EngineeringMode`**；
- 叶子密钥必须是 **RSA-2048**（4096 时 PKCS#1 恢复只保留 256 字节，会先撞长度检查）；
- 签名校验：`00 01 FF…FF 00` 去填充后与 `SHA-256(body)` 逐字节比对；
- DID 末两字节 `11`（零售）在 `0xe478` 被单独检查。

所以"自签链能过"这个假设基本可以放弃：**必须是能对上那两个 pin 的叶子证书 + 对应私钥**（三星工程证书）。
自签最多把解析推进到校验层（我们已经到 `0xf02b0010`），最后一关必然失败。

### 检索结论（找泄露）

- GitHub 代码搜索 `ENGRSS0002` 只命中上面这个审计仓库（它也只是分析，没有证书/私钥）；
- 搜 `engmode token` / `EngineeringMode certificate` 没有公开的证书或私钥；audit 自己的结论是
  "需要一份本机可接受的 mode-3 token"，同样卡住；
- 因此**目前公开渠道没有可用的 EM 工程证书**。要过这一关，现实选项是：找有服务账号的工具/店家代签，
  或者等有人放出 `em.img` 里的 pin 对应私钥。

## 43. 「把二进制位改小」能不能行？—— 不能，因为计数器不在用户区

先把语义理清：我们要的不是"让 BL 认为已解锁"，而是**让 ARB 接受比 10 低的镜像**（One UI 7 = 二进制 9）。
这需要把设备侧的 rollback 计数从 10 改小。

证据与推理：

1. 设备侧计数是 `ro.boot.rp = 10`，由 **BL 在启动时写入**，用户区改 prop 无效（BL 从不读 prop）。
2. PIT 里**没有 ARB/RP 分区**：查 `pitmap.json` 只有 `SEC_EFS/BKSECAPP/STORSEC/UEFISECAPP/SECDATA`，
   没有 arb/rollback 类节点 → 计数不在可 dd 的分区里。
3. Download 界面显示的是分组件计数 `RP SWREV: B10/K10/S10`，由 BL 内的常量与设备侧值比对，
   设备侧值属 TZ/RPMB 一类一次性/单向存储（与 KG 状态同一层）。
4. 想靠"改镜像里的 binary 字段"绕过也不行：那会破坏 AVB 摘要，locked 设备必须三星原签
   —— 而原签镜像的 binary 字段本来就写死 9。

也就是说 **ARB 和 AVB 是两道独立的门**，闯 One UI 7 要同时过：ARB（TZ 计数）挡在前面，
AVB（原签）挡在后面。两者都不在我们能改的层（除非有 TZ 写能力，即又回到 KG/EM 那条线）。

现实结论：**二进制位改不了**。要 One UI 7 只能等"能写 TZ 状态"的手段（KG 进 1/4 或 EM token）；
一旦有了写能力，其实也就不需要 One UI 7 了 —— 那两样本身就能解锁/放行 custom 镜像。
所以 One UI 7 属于"回头路"，不是"捷径"。

## 44. EDL 能不能不动硬件、只换根线？——机制上可以，但本机未验证

**EDL 线的原理**就是"免拆版的短接"：USB 线里串一个 **约 300 kΩ 电阻把 D+ 拉到 GND**（带开关），
开机时 charger/PMIC 检测到该状态，SoC 直接进 Sahara（9008），BL 不参与。所以它不是软件技巧，
不需要 Root、不需要解锁、也不看 KG —— 这正是它能绕 `-5` 的原因。

要点与限制：

1. **是否吃这根线取决于机型**。网上对面 S918U 的教程写的是"关机 → 按住音量上+下 → 插 USB"，
   不行才短接测试点或用 EDL 线。本机实测"音量上+下 + 插 USB"进的是 **Download 模式**（Odin），
   `reboot edl` 和 misc BCB 也都无效，所以 S918B 大概率需要测试点或 EDL 线，**线能不能触发未知**。
2. **firehose 必须是签名的**。已确认 `Alephgsm/SAMSUNG-EDL-Loaders` 公开提供
   `S918B_Loader_alephgsm.com.elf` 和 `SM-S918B_prog_firehose_ddr.elf`（759,948 字节），型号精确匹配。
3. **EDL 不等于解锁 AVB**。我们已用 root `dd` 实证：把 patched `init_boot` 写进去，开机会 Security Error。
   EDL 只是把同样的写入变得不依赖 root，**custom 镜像仍然过不了 AVB**。
4. EDL 的真实价值：**救砖 / 任意读分区 / 配合服务工具做 FRP-KG 类修复**；
   不少商业工具（UnlockTool、Chimera 等）声称能在 Qualcomm 三星上通过 EDL 处理 KG，
   这条要验证的是"它们是否真能改到 TZ 侧状态"，而不是仅清 App 数据。

结论：**买根 EDL 线试是划算的**（几十块钱、不动手机、失败无损失），但要预期它换来的是
"读写能力 + 救砖"，不是"直接解锁"。真正决定成败的仍是 TZ 状态。

## 45. 检索「成功案例」的结果：进 EDL 有线可行，但"EDL 刷 custom 能开机"基本没人成功

分两件事查，结论差别很大。

**A. EDL 线能不能进 9008（本机同代）—— 有成功案例。**
YouTube《EASY STEP BY STEP TUTORIAL SAMSUNG EDL MODE | S25 | S24 | S23 with EDL CABLE》明确是
S23/S24/S25 用 **EDL 线**进 9008 的步骤（视频里挂了 Amazon 链接），评论区还提到"EDL v2 无按键线，
可能就是老的 300k 电阻法"。所以**线这条路不用拆机、可用性有旁证**。

**B. 在 locked BL 上通过 EDL 刷 custom 镜像并开机 —— 基本没有成功案例。**
- XDA《How to flash custom rom within EDL mode?》：评论直接说
  *"There's no way to flash custom roms within EDL mode if the bootloader is locked"*；
- 同一帖有人（Poco X4 Pro，同样 locked）实测：EDL 刷完工具显示 `FLASHING SUCCESS`，
  开机却是 **"SYSTEM HAS BEEN DESTROYED"** —— 和我们 dd 写 patched `init_boot` 得到的
  Security Error 是同一类结果，都是 AVB 在拦；
- droidwin 那类"Supports Locked Bootloader"的标题，指的是**刷原厂分区**，不是 custom。

**C. KG 锁通过 EDL 清除**：MobiFirms 等把它做成了付费远程服务（"KG Lock Removal | Remote USB Unlock"），
但**没有公开技术文章**说明它到底动了什么（EDL 写分区、还是真的碰了 TZ 状态）。
这是唯一还值得向服务商验证的空白点。

### 结论

买线值得（几十块、不动手机），但要认清它能给的是：**进 9008、救砖、任意读写、以及做实验**
（例如一次性把 patched `vbmeta`+`init_boot` 一起写进去，验证是不是真的只能到 "SYSTEM HAS BEEN DESTROYED"）。
**它不会让 custom 镜像开机**，除非顺带解决 AVB —— 而 AVB 又回到了 TZ 状态。

## 46. 再挖本地路径：8 条新线索（含一条已经动手的）

「本地还有没有别的办法」清点了一遍，剔除已证死的，剩下这些**还没试过**的：

### L1（已动手）EM 层直接改位图，绕过 token
审计里写明 TA 有 **bitmap 设置 handler（`0xea8c`）**，按 mode 列表（u16 数组，上限 0x80）逐位设置。
如果能从 HLOS 直接发这条命令，**EM bit3 就能在没有 token 的情况下置位**。
已确认可以走 `EngineeringModeWorld::emProcess(em_req_payload_t*, len, rsp, len*)`（`+8` 是 cmd 字段），
工具 `scripts/emcmd`（`/tmp/emraw`）能正常调进 TA 并返回 0，但**cmd 编号还没对上**
（TA 的 cmd 是大值，例如 `emGetTokenRequest` 用 `0x21c7d`，不是 1..37；1..37 是 T3 子命令），
所以位图暂时没被改到（`getModesbit` 仍全 0）。下一步：从 `emGetModesbit` 的封装里读出它用的 cmd，
再比邻找 bitmap 那条。

### L2 同一二进制位内降级 ABL（不去 One UI 7）
`AFZE/AFZF/AFZG` 都是二进制 A（ARB 不拦）。samroot23 说新的 ABL 把 Download 长按解锁入口换成了
`return false`，但**下层流程还在** —— race 到更早的 A 版 ABL（比如 2026-05 的 AFZE1）可能入口还是活的。
成功后就是正常解锁（orange、AVB 关）。代价：SamFrew 只给整包（约 16 GB）。

### L3 `sendFuseCmd`
HAL 里还有这条没调过，名字带 "Fuse" —— 有可能是让 TA 烧 LCS/EM 相关位。可用 kgcall/lite 试。

### L4 `recoveryItl`
HAL 方法，语义未知（ITL ≈ integrity）。若它会让 TA **重算 steady 的完整性字段**，
那我们伪造的 ESI 块就能被"洗白"，EM 那条直接通。

### L5 KG 侧喂假 regInfo
`verifyRegistrationInfo`(26) 现在回 264（数据无效）。regInfo 结构可从 MITM 抓的
`getKGStatus`/policy 流程里反推，喂进去看 264 会不会细化成"签名错/字段错"。

### L6 HLOS 堆溢出（审计 C-2）
emservice HAL `getBytes` 直接 `memcpy(dst, …, mLen)` 不校验长度，dst 是 `calloc(1,0xC800)`。
只能拿 HLOS 代码执行（我们已有 root），但可用于**让 HAL 以更宽权限调用 TA**。

### L7 EDL + patched vbmeta 一次性实验
把 `vbmeta`（flags 置验证关闭）和 patched `init_boot` 一起通过 EDL 写入，验证是不是只能到
"SYSTEM HAS BEEN DESTROYED"。需要线。

### L8 `AT+ENGMODES` 原生 AT 通道
`SatsService` / `EngModesCmdHelper` 会组 `0,2,` 前缀丢给 `commandForEss`。若能让 modem 认，
可能绕开我们卡住的 binder/ESS 封装，直接喂 ESS 命令。

**排序**：L1、L4（都不需要外部资源）＞ L2（16 GB 下载）＞ L3、L5 ＞ L6、L8 ＞ L7（需买线）。

### L1 进展：payload 布局摸到了（`preparePayload`）

`emGetModesBit` 的实现顺序确认了请求怎么造：

1. `preparePayload(21, 1)` —— 参数就是 **(cmd, sub)**，返回值 0 才算成功；
2. 该函数把 header 写成 **`01 15`**（byte0=版本 1，byte1=cmd），sub 放别处；
3. 接着 `em_read_to_steady(3, buf, 0x2c00)` **自己读 steady idx3**；
4. 再从 steady 里把字段灌进 payload，最后 `em_tlc_send`。

也就是说：**只调 `preparePayload` 不够**，还要自己读 steady 并填字段。
我们目前的 `emProcess` 调用返回 `rc=0 / rlen=0`（空跑），原因就在这。
工具 `scripts/emcmd.cpp`（裸构造）和 `/tmp/emcmd2`（走 `preparePayload`）都留着。

下一步最省事的做法：既然 `emGetModesBit` 是导出的，就直接照它的顺序抄一遍，
把 cmd 换成疑似 setter（`22`）再试；或者干脆找 TA 里 bitmap handler 的真实 cmd 常量。

## 47. L1/L4 实测记录（都推进了，但都被"格式"挡住）

### L1：请求结构全解，且证明 opcode 只有一条
把 `emGetModesBit` 逐条抄出来后，结构完全清楚：

- payload header 是 **`01 <cmd>`**（byte0 版本、byte1 cmd，get modes 用 `0x15`）；
- 然后是 `p+0x5f1` 的 flags、`p+0x25` 的 singleId、`p+0x611`（steady idx2 副本）、
  `p+0x1f07d`（steady idx3 副本），总长 `0x21c7d`；
- `em_tlc_send(payload, len=0x21c7d, rsp, &cap)`，**第二个参数是长度不是 opcode**；
- 全库只有一条 opcode `0x21c7d`（13 处调用点都是它），真正的命令就是 header 里的 cmd 字节。

实测：`preparePayload` 返回 0、`em_read_to_steady` 两次都返回 0，但 `em_tlc_send` 返回 **0 且 rlen=0**，
而同进程紧接着调真正的 `emGetModesBit` 能拿到 `0xf02d0010`（TA 真的应答了）。
→ 说明手搓的 payload 还没被 TA 接受，最可能是**少设了 header/长度字段**或需要 `emInit` 先建会话
（我们这边 `emInit` 仍失败）。工具：`scripts/emset.cpp`。

### L4：`emRecoveryData` 存在且走到了 ITL 解析
`EngineeringModeWorld::emRecoveryData(const u8*, u32)` 是导出的，内部等价于
`preparePayload(13,1)` + 把 blob 拷到 `p+0x11615`（长度写 `p+0x11611`）+ `em_tlc_send`。

TA 侧（cmd 13 → handler 0x8900）的字符串证据：`Unknown ITL magic(%02x/%02x/%02x)`、
`please check recovery message length`、`em_crypto_verify_recovery_data`、`em_esi_recovery`、
`Recovery counter is invalid(core rcounter %d, esi rcounter %d)`、`Recovery counter type`。
即它是 **ITL 格式 + 恢复计数器 + 签名**，且计数器要和 ESI 里的一致。

实测（错误码在动）：
- 原始 steady 块（11264）→ `0xf0050014`
- 以 `ITL` 开头 + 1024 零 → **`0xf01e0010`**（换了分支，magic 被认）
- `ITL` + 32/64/256/2048 零 → 都是 `0xf01e0010`；`ITL` + 11264（或 ITL+整块）→ `0xf0050014`

结论：ITL magic 有效，卡在长度/计数器/签名。**这条路是活的**，下一步要像 token 一样把 ITL 结构摸出来
（先找 `0xf46b7` 处 magic 比较之后的解析顺序，再看恢复计数器的字段位置）。

### L4 结构线索（静态）

`ITL` 的解析不在简单比较里：TA 里 find 到的 counters 是**按字节解析 + `#0xffffffdf` 掩盖大小写**
（`cmp w8,#0x49` / `cmp w10,#0x4e` / `cmp w11,#0x41` / `cmp w12,#0x58` / `cmp w22,#0x30` …，见 `0xece60`–`0xed0b8`），
像是 **ITL = 文本/令牌语法**（`I`,`N`,`A`,`X`,`0` 这些分支），而不是二进制 TLV。
配合"恢复计数器必须和 ESI 里的 core rcounter 一致"，下一步应该按语法逐字符反向，
先让 `0xf01e0010`（长度/语法错）变成"计数器错"。

试过的变体：`ITL`+零（各种长度）→ `0xf01e0010`；`ITL`+11264 或 `ITL`+u32(1)+整块 → `0xf0050014`（更靠后但被拒）。

### L2 的下载被 Cloudflare 挡住

SamFrew 的文件链要走 CF 的 JS 挑战，`curl`（含完整浏览器头）只拿到挑战页；
`samloader` 走 FUS 也 403（上游 auth 变了）。要拿到 AFZE1 整包得用真浏览器（或过 CF 的 cookie）下载，
这条暂时挂起，等 L4 有结论再回来。

### L4 继续：`0xf01e0010` 的来源

按 "please check recovery message length"（VA 0xf3c99）找到引用点，它在 **ESS/recovery 家族（0x13d7c 附近）**，
错误码形态是 `0xf04a00xx`；相邻还有 `0x1514/0x1515` 之类的上下文偏移和 `0x133000+0x3a8` 的指针表。
说明 recovery 数据先过长度/长度-计数器校验，再进签名（`em_crypto_verify_recovery_data`）。

我们拿到的 `0xf01e0010` 更早（另一处），而 `0xf0050014` 是最初的解析失败。
下一步需要一个能打印"走到哪一条分支"的探针（目前只能靠错误码区分），
建议顺序：先把长度和 ITL 语法按 `0xece60`–`0xed0b8` 的字符分支反出来，再对齐计数器。

### L4 修正：magic 不是 `ITL`，而是和 token 同一处常量 `3f e4 e4`

在 0x7e0c 处：`memcmp(ctx+0x2ff8a, 0xf43de, 3)`，而 0xf43de 就是之前 token 那条线里的
`3f e4 e4`。日志字符串 `Unknown ITL magic(%02x/%02x/%02x)` 在 0xf43e2（紧跟常量之后），
所以日志里打印的是 **被比较的那三个字节**，不是我们以为的 "ITL" 字面量。

但把 `3f e4 e4` 放到开头（以及 `[len]+magic`、`[4 字节]+magic`、`magic+[计数器]` 四种排布）**都还是 `0xf01e0010`**。
结合周围字符串：这条路径叫 `EM_CMD_RECOVERY_ESS_V1` / `EM_CMD_REQ_RECOVERY_ESS_V1`，
附近还有 `em_ess_encrypt_message`、`em_crypto_verify_cert` —— 高度怀疑 **recovery 数据是 ESS 报文格式**
（要被证书加密/包一层 ESS 外壳），所以直接塞裸数据连 magic 都对不上位置。

若成立，L4 最终也会回到"需要那张工程证书"。这条先记着，等证书线索有进展再回头。

## 48. L2 实测：单刷 ABL 被 XBL 判 hash 不符 → 必须整 BL 一起换

AFZE1 整包下完（Bifrost，16.2 GB，自动解密成 zip），取出 `BL_...AFZE1....tar.md5`，
解压 `abl.elf`（4 MiB）后单独刷入 `abl` 分区：设备没进系统，Download 界面报 **hash 不对**
——说明 ABL 的完整性由 XBL（或同批镜像）校验，**只换 ABL 不成立**。

于是改走"整 BL 一起刷"：BL tar 里 31 个镜像按 `pitmap.json` 映射成 30 个分区，
全部解压备好（`/tmp/afze_bl/`）。注意 heimdall 的两个坑：

1. 参数列表最后一行必须有**换行**，否则最后一个 `--PART` 缺文件名 → 打印 usage 并报
   `Missing parameter for argument: --XBL`；
2. 一旦会话失败，设备侧状态变脏，之后连单分区都会 `Protocol initialisation failed`，
   需要在手机上重新进一次 Download（强关 → 音量上+下插 USB → 音量上）。
3. 现用 `batches`（6 分区/批）拆分，待重新进 Download 后继续。

原 ABL 已备份：`/data/local/tmp/abl.bak`，sha256 `287599f5…`（= ZH3 官方镜像），可随时回退。

## 49. L2 结论：AFZE1（最早的二进制 A）长按解锁同样是死的 —— 整 BL 换完也无反应

完整过程与结果：

1. 单刷 `abl` → 开机报 `Calculated Hash of (abl) … (VBMETA) …`，说明 **`abl` 的哈希由 `vbmeta` 校验**，
   单独换 ABL 必挂；
2. 改刷整套 AFZE BL（30 个分区，含 XBL/TZ/vbmeta）→ `abl` 那条消失、换成 `boot` 不符
   （因为 AP 还是 ZH3），符合预期、且不影响 Download 内测试；
3. 在这个状态下**长按音量上 7 秒，屏幕毫无反应** —— 没有解锁确认页。

所以 **AFZE1 的 ABL 也已把长按入口判死**（不是后来才补的），L2 这条本地捷径判负。
附带确认了两个事实：Samsung 的 BL 分区被 `vbmeta` 哈希串联（不能单换任何一件）；
`-5` 之外的"hash 不符"只是 AVB 开机校验，不影响进 Download。

回退已完成：整套 ZH3 BL 刷回，设备正常开机、`green`、ABL sha256 回到 `287599f5…`（与官方一致），
临时 root 也已恢复。

### 对本地路线的意义

L2（换旧 ABL）走完并失败，剩下的本地线索里 **只有 L1（EM 位图直改）、L4（recovery/ITL）、
L3（sendFuseCmd）、L5（假 regInfo）、L8（AT+ENGMODES）** 还有意义，都离不开 TZ 状态。

## 50. L5 试了一轮：`verifyRegistrationInfo` 只有"喂字符串才进解析，但一律 264"

`kgcall` 支持 `str:` 参数后按各种形状喂 `verifyRegistrationInfo`(26)：

| 形状 | 结果 |
| --- | --- |
| `ba:32 ba:32`、`ba:512 ba:256`、`ba:4096 ba:256`、`ba:1024 ba:1024`、`ba:2 ba:2`、`ba:16 str:x` | **SIGKILL**（回空） |
| `str:{} ba:256`、`ba:256 str:{}`、`str:{"a":1} ba:256` | 进解析，**一律 `264`** |

结论：第一个/第二个参数里**有一个是字符串**（大概率是 regInfo 文本或 base64），另一个是签名；
但结构细节拿不到梯度 —— 264 是"数据无效"的统称，试不出更细的分支。

要真正推进 L5，必须拿到**真实的 regInfo 报文**（enrollment 时服务器下发），
只能靠 `kg_mock_setup.sh` 起 MITM 让官方客户端跑一遍完整 enroll，再从 HAL 日志看它传了什么长度/形状。
成本中等，且仍需证书才能过。**L5 暂记为"需客户端配合，单靠盲喂推不动"。**

## 51. L5 起 MITM 时踩到的两个新坑（都记下来，避免重来）

### 坑 1：`self_final.apk` 是旧版客户端的补丁，装不回新版本

kgclient 已经自更新到更新版本（base.apk 8,274,473 字节），而仓库里的 `self_final.apk` 是 6,121,360 的旧补丁。
bind 上去后直接 `ClassNotFoundException: com.samsung.android.kgclient.app.KGApplication` —— **dex 与新版本不匹配**。

重建方法（本次已验证可行）：

1. 先 `umount` 掉 bind，把当前 `base.apk` 拷出来；
2. `apktool d` 后按新版类名打补丁：pinning 的两个 TrustManager 现在在 **`smali/p8/a.smali`、`smali/p8/b.smali`**（不再在 `l4/b`），
   两个 `checkServerTrusted(...)V` 改成 `return-void`；
3. pinning 配置类(`p8/d`) 里"列表为空就抛异常"的 `:cond_3` 分支改成返回空数组；
4. `apktool b -f`（**必须 `-f`**，否则 apktool 3 会走缓存、产出残缺 dex 又崩在 ClassNotFound）。

### 坑 2：组件全在 manifest 里 `enabled="false"`，`pm enable` 又改不动

Samsung 把这些组件默认关掉、由 App 运行时自己 `setComponentEnabledSetting`。而 **`pm enable/disable` 对 kgclient 一律抛
`SecurityException: Cannot disable a protected package`**（shell 和 root 都一样），
`packages.xml` 还是 ABX 二进制格式，手改也麻烦。

后果：装好补丁后**无法拉起 UI**（`am start ... LaunchActivity` → `does not exist`），
广播（CONNECTIVITY_CHANGE / TIME_SET / BOOT_COMPLETED / SERVICE_STATE）也全都没反应 —— receiver 同样被禁用。
所以 MITM 环境虽然起着，但客户端根本不发请求（`kg_mock.log` 为 0 行）。

**下一步**：必须把旧补丁里"App 启动时自己启用组件"的那部分代码移植到新版本
（旧版是在 `l4/b` 的静态方法里，新版该文件变成了接口，等价逻辑/调用点在 `com/samsung/android/kgclient/utils/k.smali` 一类工具类里），
让 App 自己把 receiver/activity 打开，之后才能跑 enroll 流程。

## 52. 打通「新版本客户端 + 组件启用」（重要，长期卡点已解）

这一轮解决的是之前一直没解决的三个硬问题，虽然 enroll 还没跑起来，但基础通了：

1. **旧补丁 dex 不匹配** → 按新版本类名重建（pinning 的 TrustManager 现在在 `smali/p8/a.smali`、`smali/p8/b.smali`；
   配置类 `p8/d` 的"空列表即抛"改成返回空数组）。`apktool b` **必须加 `-f`**，否则缓存会产出残缺 dex。
2. **组件全是 `enabled="false"` 且 `pm enable` 对受保护包无效** → 直接在 `KGApplication` 里注入一个
   `enableAll(Context)`（数组 + 循环 `setComponentEnabledSetting`），在 `onCreate` 里调用。
   进程一起来就把 10 个组件打开，`am start ... LaunchActivity / BrowserEnrollmentActivity` 都成功了。
3. **`apply_kg_patch.sh` 两个坑**：目标文件是 root:root 644，`adb push` 会被拒（先在 root 里 `rm` 再 push）；
   bind 会被占用导致 `umount` 失败（先 `kill` 掉 app 进程，再用 `umount -l`）。

### 现状与新的卡点

- 补丁版 App 能正常起，`kgtaserv` 初始化 OK、`getKgState` 读得到 2（Active）；
- `BrowserEnrollmentActivity` 能打开，但界面停在 **"Please wait…"**，`kg_mock.log` 一行都没有
  ——**客户端还没发任何 HTTP**；
- 试过 `settings put global device_provisioned 0` 再重开，无变化；
  `[KGAgent]EnrollmentCommon` 构造完就没有后续日志。

下一步应顺着 `EnrollmentCommon` 的流程看它在等什么（很可能在等"KG 未登记/checking"这种前置状态，
或等某个系统回调），再决定是补前置状态还是直接在 smali 里跳过等待。

## 53. "Please wait…" 的根因：enrollment 需要一个 `browserEnrollParam`

反到 `BrowserEnrollmentActivity.onCreate`：

- 它先读一个**静态 Intent 字段**里的 `browserEnrollParam`（key 同名），读不到再退回 `processors/b -> a` 这个字符串；
- 两者都空 → 界面就停在 `pleasewait`（"Please wait…"）进度条，不会发起任何网络请求；
- 参数正常应由 **KGSP lookup** 的返回带出来（`m8/a` 里的 `/gksl/v1/lookup/`）。

而 lookup 没被触发的原因也清楚了：`KGEventService` 收到 HANDLE_SERVICE_INTENT 后先 `getTAState`，
读到 **Active** 就直接 `[STOP]` 收工 —— Active 意味着"已登记"，所以走不到 enroll 那段。

用 `am start --es browserEnrollParam https://...` 试过：无效，因为代码读的是**静态字段**而不是启动 Intent 的 extras；
带 extras 启动后 Activity 会自己 finish。

### 下一步（三选一）

1. 改 smali，让 `onCreate` 优先读启动 Intent 的 extras（最省事，改完就能喂 mock URL 观察 WebView 行为）；
2. 让 TA 状态变回非 Active（`resetKgInfo` 无效，得伪造"未登记"）；
3. 走 lookup：直接调用 `m8/a` 的 lookup 逻辑（需要构造请求、还要过 TLS/pinning —— pinning 已绕过）。

## 54. 方案 1 成功：`browserEnrollParam` 现在能从启动 extras 传入

改法：`BrowserEnrollmentActivity.onCreate` 里把"读静态 Intent 字段"换成
`getIntent().getStringExtra("browserEnrollParam")`（保留原来的 `processors/b.a` 兜底）。

效果确认（`am start ... --es browserEnrollParam "https://gsl.samsunggsl.com/enroll"`）：

- 进度条被隐藏、按钮显示出来，`onCreate → onStart → onResume`；
- **1 秒后 App 自己 `finishActivity`** —— 这是设计行为：类名就叫 BrowserEnrollment，
  拿到 URL 后会交给**浏览器**打开，自己退出。

### 新问题：交给浏览器后没有产生流量

`kgreq.log` 里没有任何 `enroll` 请求。原因很可能是 **Chrome 用自己的信任库**，
我们注入进 conscrypt 的 CA 对它无效（之前能抓到的都是 WebView 流量，`osname=android_webview`）。
而 Chrome 在看不到受信证书时不会发出可被我们观察的请求（或直接报错页）。

下一步二选一：
1. 把 CA 也装进"用户证书"（设置 → 安全 → 加密与凭据 → 安装证书），Chrome 才会信任并让我们抓到；
2. 或在 smali 里把 `d(url)` 改成用 `WebView` 内嵌打开（走 conscrypt，现有 CA 就够）。

## 55. 链路打通 + 两个现实结论（Chrome 不认我们的 CA；lookup 仍是未登记）

### 链路现在真的通了

用 `browserEnrollParam` 传 URL 后：Activity → 交给 Chrome → Chrome 打我们的 MITM。
第一次卡在 **Chrome 首次运行向导**（`FirstRunActivity`，一直在 "Checking info…"），
而 443 全量 iptables 影子会把它拖死 —— 临时 `iptables -t nat -F OUTPUT` 让它过完向导后就正常了。

### 结论 1：Chrome 不信任注入的 CA

页面直接报 **`NET::ERR_CERT_AUTHORITY_INVALID`**（我们只把 CA 注进了 conscrypt，Chrome 用自己的信任库）。
点过一次 `Advanced → Proceed` 后请求就能进来（`kgreq.log` 出现 `GET gsl.samsunggsl.com/enroll`）。
所以之后每次换 URL 都要点一次，或者改成内嵌 WebView。

### 结论 2：真实 lookup 仍是 `registered:false`

Mac 上直连真实服务端（绕开 pinning）：

```
POST https://gsl.samsunggsl.com/gksl/v1/lookup/device/kg
→ 200 {"serviceInfo":{"registered":false,"serviceIdentifier":"KG",
        "serviceUrl":["http://eu-gslu.samsunggsl.com:80","https://eu-gslu.samsunggsl.com:443"]}, ...}
```

和我们 MITM 抓到的历史结果一致：本机在任何租户里**都没登记**，所以服务端也不会下 policy，
enroll 页面对它来说就是"新设备"。

### 下一步

1. 用真实 `serviceUrl`（eu-gslu）当 `browserEnrollParam` 走一遍，看它是引导登录/输入 PIN 还是直接 enroll；
2. 顺手把 WebView 内嵌方案做了，省掉每次点证书告警；
3. mock 侧要按 eu-gslu 的真实路径补 handler，否则页面出来也是 404。

## 56. 让 Chrome 信任 MITM 证书（不用再点 Proceed）+ eu-gslu 要单独接线

Chrome 的问题是**不认注入到进程命名空间里的 apex CA 副本**（它只信系统/自身启动时拿到的）。
两个改动合起来就通了：

1. **每次运行前重新往 zygote 的 mount ns 注入 CA**，并**重启 Chrome**（`am force-stop com.android.chrome` 后再拉起），
   这样 Chrome 及其 network service 从 zygote 继承到注入后的 `/apex/com.android.conscrypt/cacerts`，
   `ERR_CERT_AUTHORITY_INVALID` 消失，mitm 日志能直接看到 `GET https://gsl.samsunggsl.com/enroll`。
2. 另外把 `/system/etc/security/cacerts` 也整体 bind 了一份带 CA 的副本（对别的进程兜底），实测不影响 Chrome。

`eu-gslu` 走的是另一个反向代理实例（8445），但 iptables 只把 443 全量转向 8443（并把 pinning 主机的固定 IP 转 8444），
所以直接开 eu-gslu 会因为**SNI 与证书不匹配**再次报隐私错误。补一条按 IP 的规则即可：

```bash
iptables -t nat -A OUTPUT -p tcp -d 52.211.134.225 --dport 443 -j REDIRECT --to-ports 8445   # eu-gslu 的 ELB IP
```

注意 eu-gslu 是 ELB，IP 会漂，换 IP 后要重加。加完后 `curl https://eu-gslu.samsunggsl.com/` 能通（404 是服务端正常反应）。

## 57. 让 Chrome 走 MITM 的正确配置（gsl 已通）+ eu-gslu 被 DoH 卡住

**已通的部分（gsl.samsunggsl.com）**：关键是
① 每次测试前往 zygote ns 重新注入 CA，② 重启 Chrome，③ 用 `--set confdir=/tmp/mitmCA` 固定 CA（否则每次重启 mitm 都换 CA，信任就断）。
做完这三步，Chrome 打开 `https://gsl.samsunggsl.com/enroll` 不再报证书错，mitm 日志直接能看到请求。

**还没通的部分（eu-gslu）**：

- 方向是对的：给 `/system/etc/hosts` bind 一份写了 `127.0.0.1 eu-gslu.samsunggsl.com` 的副本，
  再加 `iptables -t nat -I OUTPUT 1 -p tcp -d 127.0.0.1 --dport 443 -j REDIRECT --to-ports 8445`，
  `curl -k https://eu-gslu.samsunggsl.com/enroll` 就能打到 8445 并拿到应答；
- 但 **Chrome 依然报 `ERR_CERT_AUTHORITY_INVALID`**，且 mitm 日志里没有它这次的连接 ——
  典型原因是 **Chrome 自己的异步 DNS / Secure DNS(DoH) 绕过了 /etc/hosts**，解析到真实 ELB IP；
  单独给 `52.211.134.225`、`99.80.45.82` 加 IP 规则也没能命中（ELB IP 会漂）。

### 结论 / 下一步

要在 Chrome 里稳定抓 KG 流量，得先让 Chrome 不用 DoH（设置 → 隐私和安全 → 使用安全 DNS 关掉），
或者干脆回到**内嵌 WebView** 方案（WebView 走系统解析 + 我们已注入的 conscrypt，没有 DoH 问题）。
经验上后者的确定性更高。

## 58. 内嵌 WebView 方案：活动已加好，但还没接上真正的"打开浏览器"出口

新增了 `com.samsung.android.kgclient.ui.WvActivity`（最小 WebView：开 JS/DOM storage、读 extra `u`、loadUrl），
并改 `c9/d`（原来用 `Patterns.WEB_URL` 校验后发 `ACTION_VIEW`）为启动 `WvActivity`。

结果：**enrollment 实际仍然开 Chrome** —— 说明主流程的"打开浏览器"出口不是 `c9/d`
（`c9/d` 只被 `BrowserEnrollmentActivity` 用在 hint 链接的 span 上）。
真正的出口还没定位：`WEB_URL` 全库只有 `c9/d` 一处，而 `q9/d` 只发内部 Activity，
`processors/n` / `w8/b` 里是 `sendBroadcast` 为主。

**下一步**：从 `BrowserEnrollmentActivity.a()`（清状态 + 1 秒后 finish）反查它之前谁负责开浏览器，
或干脆在 `onResume` 里自己接管（拿到 param 就直接 `startActivity(WvActivity)` 并在 WvActivity 里跑流程）。

顺带：RootToolbox 这个仓库是 **TrickyStore keybox / 认证检测** 工具，对解锁 BL 没有直接帮助，
但能显示 `deviceLocked` / `VerifiedBootState` / 认证根证书类型（含三星 Knox 根），可当状态诊断用。

## 59. onResume 接管成功：内嵌 WebView 跑起来了，而且真的打开了 eu-gslu 页面

做法：

1. `BrowserEnrollmentActivity.onResume` 里如果 intent 带 `browserEnrollParam`，就 `removeExtra` 后
   启动一个**已声明的** Activity 并把 URL 放进 extra `u`（新加的活动不生效，因为 PM 只在装包时解析 manifest，
   bind mount 改动要重启才认 —— 所以复用现有的 `LaunchActivity`）；
2. `LaunchActivity.onCreate` 开头加分支：有 `u` 就建 WebView、开 JS、`loadUrl` 然后 `return`，否则走原逻辑。

结果（`browserEnrollParam=https://eu-gslu.samsunggsl.com/enroll`）：

- 顶层 Activity 变成 `LaunchActivity`，**Chrome 不再参与**；
- mitm 日志出现来自设备的请求（`127.0.0.1:57xxx GET https://eu-gslu.samsunggsl.com/...`），
  **没有证书错误**（WebView 走 conscrypt，正好用上我们注入的 CA）；
- 页面真的渲染出来了，标题是 **"Device Services"** —— 这是 eu-gslu 的真实页面。

至此客户端→服务端这条链路完全在本地可控了。下一步就是看这个页面要什么（登录/租户/PIN），
并在 `kg_mock.py` 里按 eu-gslu 的真实路径补 handler，观察客户端如何解析 enroll 结果。

## 60. WebView 通了，但 `/enroll` 不是真实路径（页面还是 404）

澄清一个误判：WebView 里看到的 "Device Services" 其实是 **KG 客户端自己的 Activity 标题**
（`@string/app_name`），不是页面内容。真实请求只有 `GET /enroll`，命中 404；
从 Mac 直连真实服务端枚举 `/`、`/kg`、`/kg/v1/enroll`、`/device/enroll`、`/sal`、`/enrollment` 等**全部 404**。

所以缺的是**正确的 enroll 页面 URL**。线索在代码里：

- `BrowserEnrollmentActivity` 的 param 来自 `processors/b.a`（静态字段）；
- 该字段在 `h8/c`（KGSP action 处理）里按枚举分支赋值，其中只有 `URL_FORBIDDEN` / `NON_KG` 是固定串，
  正常情况赋的是**服务端消息里带的 URL**（`h8/c` 里那个 `v5`）；
- 也就是说：**只有真正跑过一次 KGSP 交互（lookup→policy/action 消息）才会拿到 URL**，
  硬猜路径没用。

### 下一步

1. 让客户端自己做一次 lookup：现在组件和 WebView 都通了，剩下的是把"Active 不触发 lookup"绕开
   （临时改状态 or 直接调用 `l8/a` 的 lookup 方法）；
2. 拿到服务器回的 action 消息后，`processors/b.a` 就会有真实 URL，WebView 直接打开它，
   mitm 也能看到完整交互；
3. 之后再谈在 mock 里伪造这些消息。

## 61. 突破：客户端自己发出了真实 lookup，并接受了我们的应答

三处改动串起来后，链路第一次跑通：

1. `KGApplication` 里 postDelayed 4 秒后调 `l8/a.k(true,false)`（用独立 Runnable `LookupKick`，
   因为直接在 onCreate 调会撞 `l8/a.<clinit>` 的 `ExceptionInInitializerError`）；
2. 修好之前踩的 VerifyError：`p8/d` 里"空 pinning 列表就 return 空数组"补丁**打错方法了** ——
   打到了 `d(String)`（返回 X509Certificate），正确的是 `c(String)[LTrustManager;`；
3. `kg_mock.py` 的 LOOKUP_BODY 按真实报文修正：`serviceIdentifier` 必须是 **`KG`**（之前填成包名，客户端回
   "lookupservice info is not available or not KG"），`registered:false`，`serviceUrl` 指向 eu-gslu。

结果（logcat 可复现）：

- `POST gsl.samsunggsl.com/gksl/v1/lookup/device/kg` 真的发出去了；
- 客户端自己开始 `setEnabledSetting` 打开 LaunchActivity / BrowserEnrollmentActivity；
- 应答被解析：`HttpClientSync ... response code : [200] -> within acceptable code range`，`@gslLookup - end`。

卡点：解析完就结束了，**没有自动拉起 enroll 界面**，也没有后续 getKGStatus。
说明 `registered:false` 之后还需要别的字段/状态驱动（或需要 policyRequired 等），下一步从 `GSLManager` 的
`composeGslDeviceRequest` / 回调分支看它拿到 false 后走哪条分支。

## 62. 走到 getKGStatus 了，但请求瞬间失败（3ms，且没到 mitm）

把 `LookupKick` 改成调 `l8/a.j("",false,false,cb)`（这个方法内部就是"先 lookup 再 getKGStatus"），
并补了一个空实现的 `Ll8/b` 回调 `NullCb`（之前传 null 时是 `onResponse - null callback`）。

现在 logcat 能走到：

```
NetworkManager: @getKGStatus
NetworkManager: @makeSyncPostCall - EU-GSLU / KG_STATUS
NetworkManager: @onResponse - FAILURE        ← 3ms 内就失败
```

TA 侧也真的被调了（`getClientData` / `getTAInfo` / `getKgId`），说明请求体在正常组装。
但 **mitm 完全没收到这个连接**（`kg_mock.log` 无新行），3ms 也排除了 DNS 慢解析。

怀疑方向（按可能性）：
1. 客户端给 EU-GSLU 用的是**存下来的 serviceUrl 带 `:443`**，拼路径时可能拼成非法 URL；
2. 或者走的是另一套 SSLContext / pinning TrustManager（我们只绕了 MPS 那两个 `p8/a`、`p8/b`），
   握手在本地就被拒；
3. 也可能 EU-GSLU 域名解析到了我们没覆盖的 IP（hosts 已指向 127.0.0.1，但 App 可能缓存过旧解析）。

下一步：在 `HttpClientSync` 失败分支打日志把完整 URL 打出来（或 hook `makeSyncPostCall` 打印），
先确认 URL 形状，再判断是 URL 拼接还是 TLS 的问题。

## 63. 找到了 gap 的正解：不是路由，是**证书 SNI 不匹配**；顺带确认 hosts 对 App 无效

关键诊断手段：在 OUTPUT 加 `iptables -I OUTPUT 1 -p tcp --dport 443 -j LOG --log-prefix KGDST`，
抓 `dmesg` 里的目的地址。结果发现每次都是**真实 ELB 的公网 IP**（`4.150.x`、`52.168.x`、`40.79.x`、`74.151.x` 轮换），
而不是我们 hosts 里写的 `127.0.0.1` —— **`/system/etc/hosts` 的 bind 对 App 完全无效**
（`ping` 也一样解析到公网 IP，重启 netd 后依旧）。

这解释了为什么 3ms 就失败、mitm 一条日志都没有：所有 443 都被通用规则转到 **8443**，
而 8443 的反向上游是 **gsl**，于是给 `eu-gslu` 的握手用了 **gsl 的证书** → SNI 与证书不符 → 客户端直接拒。

### 结论与修法

不需要再跟 IP 赛跑。既然通用规则会把任意 443 送到 8443（证书 = gsl，可被信任），
**只要让客户端用 `gsl.samsunggsl.com` 作为 serviceUrl 就行**，`/af/` 本来就由 addon 改写到真实 eu-gslu。
已把 mock 的 LOOKUP_BODY 改成 `serviceUrl=["https://gsl.samsunggsl.com:443"]`，
并删掉 App 里 `shared_prefs/KG_shared_pref.xml` 的 `KG_SERVICE_URL/KG_UMC_CDN_URL` 让它重新 lookup。

顺带发现：`KG_shared_pref.xml` 里已经存了 `SERVER_INFO_DATA`（含 `serverMsg`/`serverToken`），
说明之前那次 getKGStatus 其实**已经被 TA/客户端解析过**，只是我们没看到网络层。

## 64. 改成 gsl 地址后 URL 正确了，但 HTTPS 连接仍在 1ms 内失败（且带 mutual auth）

按 §63 的方案把 serviceUrl 改成 gsl 后：

- `RAWURL=https://gsl.samsunggsl.com:443/af/v1/sal/devices/enhanced/getKGStatus`（**URL 正确**）
- 证书这一步也过了：`CertificatePinning: certsTrusted.isEmpty() : false`（我们给 `p8/d.c` 的兜底改成
  `TrustManagerFactory("X509").getTrustManagers()` 生效了，不再抛 "Pinning data is empty"）
- 紧接着 `@setupConnection - setting mutual auth done` → `setting up connection...DONE` → **1ms 后 FAILURE**

也就是说 SSL 上下文建好了（连客户端证书都装了），但 `connect()` 立刻失败，mitm 依旧没有连接日志。
排查提示：`@post - exception : null` 打不出栈，下一步把 catch 改成打印 `getClass().getName()`，
先拿到异常类型（`SSLHandshakeException` / `ConnectException` / `IllegalArgumentException` 指向的方向完全不同）。

另外这轮还确认了一条重要信息：请求头带 `X-CLIENT-THREATEN-INFO: NOK NOK green 1 N 1 1`
和 `X-CLIENT-DEBUG-INFO: ... Checking ...`，说明我们伪造的 Checking 状态已经进到协议里了。
