# 工具链

> 当前能力/卡点/跑法总览见 `docs/summary.md`。

记录自编/自建过程，便于重来。`/tmp` 会被清，路径按此重建。

## heimdall 2.2.2（自编，刷机主力）

brew 已无 heimdall 公式，也不在 cask。用 Grimler 维护的分支（Primary 的
Benjamin-Dobell 仓库只到 1.4.2，太老）：

```
git clone --depth 1 https://git.sr.ht/~grimler/Heimdall /tmp/heimdall2
cd /tmp/heimdall2
cmake -B build -DCMAKE_BUILD_TYPE=Release -DDISABLE_FRONTEND=1 \
  -DCMAKE_EXE_LINKER_FLAGS="-framework CoreFoundation -framework IOKit -framework Security"
cmake --build build -j8
```

产物 `/tmp/heimdall2/build/bin/heimdall`（v2.2.2）。缺 framework 链接会报
`_kCFTypeDictionaryKeyCallBacks` 未定义，所以必须带 `CMAKE_EXE_LINKER_FLAGS`。

老分支（Benjamin-Dobell）在 CMake 4 下还要 `-DCMAKE_POLICY_VERSION_MINIMUM=3.5`。

macOS 上无需 root：libusb 的 detach-kernel-driver 够用（bifrost-studio 也吃这套，
但它选择拒绝共享接口并要求 root）。

## bifrost-studio（自编，备选刷机 + 离线 PIT 校验）

```
git clone --depth 1 https://github.com/sritulasiram/bifrost-studio /tmp/bfstudio
cd /tmp/bfstudio
cmake -B build -DCMAKE_BUILD_TYPE=Release -DBIFROST_BUILD_APP=OFF
cmake --build build -j8
```

产物 `/tmp/bfstudio/build/src/cli/bifrost-cli`，支持 `devices` / `print-pit` /
`inspect` / `plan` / `flash`。`print-pit` 输出带 `flash=` 与 `blocks=`，是本项目
**建映射表的主要来源**。

实测限制：

- 需 root（`osascript` + `with administrator privileges` 可拿到）；
- 对这台机器握手恒超时（`LIBUSB_ERROR_TIMEOUT`），刷写用不上；
  但 `print-pit` / `inspect` 在本地文件上照常可用。

## Bifrost（GUI，仅用于下固件）

```
curl -L -o /tmp/bf.zip https://github.com/zacharee/Bifrost/releases/download/2.1.4/bifrost-2.1.4-mac-aarch64.zip
unzip -o /tmp/bf.zip -d /tmp/bfapp && open /tmp/bfapp/Bifrost.app
```

固件落在 Bifrost 当前目录，产出 `.enc4`（加密）与解密后的 `.zip`。
`.enc4` 在 `.zip` 完整后可以删。

## FUS 探测（无鉴权，只读）

```
curl -s -H "User-Agent: Kiss2.0_FUS" \
  "https://fota-cloud-dn.ospserver.net/firmware/XSG/SM-S918B/version.xml"
```

`User-Agent` 必须是 `Kiss2.0_FUS`，否则 Akamai 返回 `Access Denied`。

下载鉴权已换新方案，老的 samloader 派生直接 401：

- `KEY_1`/`KEY_2`（`vicopx7dqu06…` / `9u7qab84…`）派生 → nonce 解不开
  （`ValueError: not a multiple of the block length`）。
- `Kiss2.0_FUS` + `newauth="1"` 头仍 401。

## avbtool（可选，造关闭校验的 vbmeta）

```
git clone --depth 1 https://android.googlesource.com/platform/external/avb /tmp/avbtool-src
python3 /tmp/avbtool-src/avbtool.py make_vbmeta_image --flags 3 \
  --padding_size 4096 --output vbmeta_noverity.img
```

`--flags 3` = HASHTREE_DISABLED | VERIFICATION_DISABLED。

## Root My Galaxy / KernelSU-Next / Shizuku

- Root My Galaxy：`soumarcelino/Root-My-Galaxy-SM-S918B`，release APK
  `Root-My-Galaxy-SM-S918B-0.6.0.apk`（sha256 `0fc93c71…e16d93`）。
  包名 `io.github.rootmygalaxy.s23ultra`，入口 activity
  `dev.busung.s25uroot.MainActivity`（不是 `.MainActivity`）。
- AFZH3 专用 ko：`soumarcelino/KernelSU-Next-SM-S918B-AFZH3` release asset
  `android13-5.15_kernelsu.ko`（sha256 `dbb8fd27…d5763`）。
- 管理器：`KernelSU_Next_v3.4.0_33294-release.apk`（包名 `com.rifsxd.ksunext`）。
- Shizuku：`RikkaApps/Shizuku` v13.6.0。启动：

  ```
  lib=$(adb exec-out pm path moe.shizuku.privileged.api | tr -d '\r' \
        | sed 's/package://;s#/base.apk#/lib/arm64/libshizuku.so#')
  adb shell "$lib"
  ```

  启动成功会打印 `shizuku_server pid is N`，`ps -A | grep shizuku` 可见两个进程。
  重启后需重来。

## UI 自动化

`uiautomator dump` + `adb shell input tap X Y`。若干注意点：

- 三星设置项的开关在右侧（x≈960），点文字无效。
- 手势条会盖住列表底部按钮（Shizuku 的「View command」就是这样点不到）。
- 刚开机 `adb shell` 会 `error: closed`，用 `adb exec-out`。
- DocumentsUI 偶发不响应点击；Magisk 场景可用「Enter image URL」+
  `python3 -m http.server` 绕过。

## UI 自动化约定

这个项目里所有界面操作都靠 `adb shell input` + `uiautomator dump`，**不要用截图**（`screencap`）
做定位或判断——`uiautomator dump` 的 XML 直接给出 `text` / `content-desc` / `bounds` /
`checkable` / `checked`，比看像素稳、快、可复现。

要点：

1. **先确认前台再点。** dump 里出现目标 `package="…"` 才动手；否则会点到桌面图标的长按菜单
   （表现为 dump 里只剩 `Launch` / `Force stop` / `Restart` 三条）。
2. **息屏时 dump 只有 `com.android.systemui`。** 先 `input keyevent 224`(WAKEUP) +
   上滑解屏，再 `input keyevent 3`(HOME) + `am start`。
3. **点文字节点的中心**，`bounds` 由 dump 里算，不写死坐标；弹窗压住时先 `keyevent 4`。
4. **开关状态读 `checked`**：Compose 的 Switch 会暴露成 `checkable="true" checked="true|false"`，
   挑「靠右且窄」的那个节点（整行可点区域的 `bounds` 宽度会到 900+，要排除）。
5. 判定结果也用 XML 文本（如 `Root Active` / `Success`），不要比对像素颜色。
6. 已有实现可参考 `scripts/grant_su.sh`（唤醒→前台校验→按文本找行→读 `checked`→必要时点开关）。

## Ghidra + REA（反编译，本机已装）

- `brew install ghidra`（12.2，自带 openjdk@25）→ `GHIDRA_INSTALL_DIR=/opt/homebrew/Cellar/ghidra/12.2/libexec`
- `npm i -g rea-agents`，`pi mcp add rea --env GHIDRA_INSTALL_DIR=... -- rea mcp`
- 用法（CLI 直接跑，不用 agent）：

```bash
export GHIDRA_INSTALL_DIR=/opt/homebrew/Cellar/ghidra/12.2/libexec
rea analyze <bin>                                # 建 Ghidra 会话并出概览
rea decompile <bin> --procedure ram:0x742f0      # 出伪代码
rea xrefs <bin> --address ram:0x11fc60           # 交叉引用
```

ABL 的 Odin 体（`.../Odin/1 PE32 image section/body.bin`）可直接分析：
`FUN_000742f0` = 刷写闸门，`FUN_000789e0` = EM 位图测试，`0x11fc60` = EM 模式位图。

## EM (工程模式) 客户端工具 `scripts/emcli.cpp`

目标：直接调厂商 EM 栈（`libengmode_client.so` → `emservice` → `engmode` TA），先做只读
（`isTokenInstalled` / `getModesbit` / `getStringModes`）再考虑 `makeTokenReq`。

构建（NDK clang，API 34）：

```bash
NDKBIN=$ANDROID_NDK/toolchains/llvm/prebuilt/darwin-x86_64/bin
$NDKBIN/aarch64-linux-android34-clang++ -O1 -o emcli scripts/emcli.cpp -ldl
adb push emcli /data/local/tmp/ && adb shell su -c 'chmod 755 /data/local/tmp/emcli'
```

已解决的两个坑：

1. `engmodeclient` 对象**不是**几 KB：构造函数从 `this+0xc` memset `0x11000`，必须给 ≥`0x12000` 字节，
   并且要把符号 `gEngmodeclient` 指向它。
2. 只调构造函数不够，方法里 `ldr x0,[this]` 取的是 `mServer`，必须再调 `getServer()`。

**未解决**：`emservice` 注册在 **/dev/vndbinder**，而 `libengmode_client` 的 ctor 会先把
`ProcessState` 绑到 **/dev/binder**，之后再 `initWithDriver("/dev/vndbinder")` 会报
"already initialized with /dev/binder"；而在 ctor 之前先 `initWithDriver` 又会在
`ProcessState::init` 里写只读页崩溃（静态/动态 libc++ 都复现）。
所以目前 `getServer()` 返回的 `mServer` 仍是 0，方法一调就段错误。下一步可选：
用 `LD_PRELOAD` 在最早时机初始化、或改用 Java `android.os.HwBinder` 走 hwbinder（HIDL）通道。

### 备用通道：Java `android.os.HwBinder` 直连 HAL（hwbinder）

`emservice` 挂在 `/dev/vndbinder`，C++ 客户端因为 `ProcessState` 已被绑到 `/dev/binder` 而连不上；
但 **HIDL 走的是 `/dev/hwbinder`**，`android.os.HwBinder.getService(iface,"default")` 能成功拿到
`HwRemoteBinder`（已实测），绕开了 vndbinder 问题。

已从 HAL 的 `Bp` 侧反出部分 transaction code（用 `llvm-nm` + 反汇编 `mov w1,#N`）：

| code | method |
| --- | --- |
| 3 | `isTokenInstalled` |
| 4 | `removeToken` |
| 5 | `getNumOfModes` |
| 6 | `sendFuseCmd` |
| 7 | `getVersion` |
| 17 | `getTuc` |

客户端：`scripts/helpers/Em.java`（反射调用，无需 hidden API 头文件）：

```bash
javac -source 17 -target 17 -classpath $ANDROID_JAR -d out scripts/helpers/Em.java
d8 --min-api 33 --output . out/Em.class && zip -j em.jar classes.dex
adb push em.jar /data/local/tmp/ && adb shell su -c 'CLASSPATH=/data/local/tmp/em.jar app_process /system/bin Em 3 3'
```

**当前卡点**：transact 发出后**一直不返回**。而且不只是这个 HAL：
对 `android.hidl.manager@1.2::IServiceManager`（hwbinder 服务管理器，必答）发 code 1 也一样挂。
`lshal debug` 对同一批服务是秒回的。

⇒ 结论修正：问题不在报文，而在**传输上下文**。`app_process` 启动时已经把 binder 进程状态
绑到了 `/dev/binder`，Java `HwBinder` 的 JNI 依赖 `hardware::ProcessState`（应走 `/dev/hwbinder`），
在 app_process 里被污染后 handle 失效，于是 transact 永远等不到回包。
试过 `Looper.prepareMainLooper()` 也没用。

可能的下一步：
- 用 `app_process` 时避免 Java HwBinder，改回 C++ 但把 `initWithDriver("/dev/vndbinder")`
  放到 `linker` 的构造阶段（`DT_INIT`）之前——目前构造函数里调仍会在 `ProcessState::init` 写只读页崩；
- 或者造一个小 native 程序，用 `dlopen` + `initWithDriver` 且 **不链接 libc++ 动态库**、不加载 libbinder
  以外的任何东西（排除命名空间污染）；
- 或者干脆走 RILD 通道，直接给 modem 发 `libengmode_server` 用的那串 OEM AT 命令。

### 直连 EM TA（`EngineeringModeWorld`，**已能跑通到 TA**）

绕开 binder/RILD：`libengmode_server.so` 里导出 `EngineeringModeWorld::*`，其底层经
`libengmode_tlc.so` → `QSEECom` 直连 `engmode` TA。工具 `scripts/emworld.cpp`：

```bash
adb push emworld /data/local/tmp/emservice   # ← 名字必须是 emservice，见下
adb shell su -c 'chmod 755 /data/local/tmp/emservice; /data/local/tmp/emservice'
```

两个**必须**满足的前置（踩了很久）：

1. **必须降权到 uid/euid 1000**：`libstork_shared.so` 的 steady 读写只在 `getuid()==1000 &&
   geteuid()==1000` 时才走正常路径，否则 helper 直接 `return -1`，`emInit` 报 0xd0010063。
2. **进程名必须是 `emservice`**：stork 的 `STORK_BIRD` 会比对进程名，别的名字会被
   `Error : Process name is error` 挡下、`Permission error!`。
   把二进制改名成 `emservice` 放在 `/data/local/tmp` 即可（不必替换 /vendor/bin）。

做到这两点后：`emInit()` 返回 **0**，TA 正常加载（日志里能看到 `engmode.b08` 被 QSEECom 载入、
命令下发、TA 应答），说明通道完全打通。

**当前状态**：`emInit` 自己就让 TA 回 `0xf02d0010`——因为它把 `steady` idx3（11264 字节）的
初始化块原样当 payload 发给 TA，而本机 steady 几乎全空（4 MB 里仅 650 非零字节）。
所以 `emGetModesBit` / `emIsTokenInstalled` 也随之返回 `0xf02d0010`
（TA 侧状态字，和审计仓库里记录的 `0xf02d0010` 一致），重试也一样 —— 需要先走正确的初始化/时间同步、
或先装 token。下一步是 `emGetStatus` / `emGetLastTokenStatus` / `emGetTimeRequest`+
`emVerifyTime` 这串，再 `emGetTokenRequest` 走 ESS。

### `scripts/eminst.cpp`（灌 token / 探格式）

`EngineeringModeWorld::emTokenInstall(u8*, u32)` 的最小驱动：读文件 → 调用。用于按 TA 的
`0x108` 记录格式人工构造 token，逐段把 TA 的错误码往前推。

```bash
$NDKBIN/aarch64-linux-android34-clang++ -O1 -static-libstdc++ -o eminst scripts/eminst.cpp -ldl
adb push eminst /data/local/tmp/eminst   # 运行名必须仍是 emservice 类，见上
adb shell su -c '/data/local/tmp/eminst /data/local/tmp/tok.bin'
```

## 灌 token 的 runbook（拿到 token 文件后照做）

**前置**：root；二进制必须**叫 `emservice`**（stork 按进程名放行），且内部会自己降权到 uid 1000。

```bash
# 1) 编译（只需一次）
$NDKBIN/aarch64-linux-android34-clang++ -O1 -static-libstdc++ -o eminst scripts/eminst.cpp -ldl
# 2) 上传并改名成 emservice
adb push eminst /data/local/tmp/emservice && adb shell su -c 'chmod 755 /data/local/tmp/emservice'
# 3) 放 token（真 token 由 ESS/工具产出，二进制格式）
adb push token.bin /data/local/tmp/token.bin
# 4) 灌
adb shell su -c '/data/local/tmp/emservice /data/local/tmp/token.bin'
# 5) 复验
adb shell su -c '/data/local/tmp/emservice'        # emInit / isTokenInstalled / modesbit
adb shell getprop knox.kg.state                    # 期望不再是 Active
```

判读：`install rc=0` 才算成功；`0xf02d0010` = token 解析/ID 阶段失败（格式不对）；
`0xd0010062/63` = steady 读失败（多半是没改名成 emservice）。

## 刷回原厂 init_boot（救急）

分区名在 PIT 里是**全大写 `INIT_BOOT`**（`/tmp/pitmap.json` 的 `map` 可查），小写会被 "does not exist in the specified PIT" 拒。
原厂镜像必须来自同版本固件（`/tmp/fwimg/init_boot.img`，sha256 应与分区原始内容一致）：

```bash
/tmp/heimdall2/build/bin/heimdall flash --INIT_BOOT /tmp/fwimg/init_boot.img
```

KG `Active` 下刷原厂内容是放行的；刷完正常开机，再重跑 `scripts/temp_root.py` 恢复 root。

## 开机 USB 默认模式（不再每次手动改）

三星的「默认 USB 配置」不是 `persist.sys.usb.config` —— 直接 `setprop persist.sys.usb.config` 会在重启时被覆盖回去
（实测 `mtp,adb` 写进去，重启后变回 `sec_charging,adb`）。真正的开关是 Secure 设置项：

```bash
adb shell su -c 'settings put secure default_usb_configuration mtp'   # 文件传输 + adb
```

可选值（取自 SecSettings 的 `usb_configuration_values`）：`none`(仅充电) `mtp` `ptp` `rndis` `midi` `audio_source`。
用 UI 也一样：开发者选项 →「Default USB configuration」→ 选「Transferring files / Android Auto」。
设完连重启两次都稳定是 `mtp,adb`（`persist.sys.usb.config` 会保持 `sec_charging,adb` 不动，属于正常）。

注意：`rndis`（USB 共享网络）在 macOS 上**没有驱动**，选了也认不到网卡；给手机供网要用 Wi-Fi 或 gnirehtet。

## KG HAL 调用（`scripts/helpers/kgcall`）

`kgcall.jar` 用 `ServiceManager.getService` + 手工写 interface token 直接 transact
（`service call` 因 descriptor 不匹配会回 ENODATA）。用法：`Main <code> [int:0|ba:32]`。

**必须先建 TZ 会话**（否则一律 `TACtx is NULL` → SIGKILL）：

```bash
adb push scripts/helpers/kgcall/kgcall.jar /data/local/tmp/kgcall.jar
adb shell su -c 'setprop ctl.stop kgtaserv; sleep 1; setprop ctl.start kgtaserv; sleep 3'
adb shell su -c 'CLASSPATH=/data/local/tmp/kgcall.jar app_process /system/bin dev.pi.kgcall.Main 12 int:0 ba:32'
adb shell su -c 'CLASSPATH=/data/local/tmp/kgcall.jar app_process /system/bin dev.pi.kgcall.Main 7 int:0'   # getKgState
```

任何参数形状不对的调用都会把 oneshot 的 `kgtaserv` 打死，需要 `ctl.stop`+`ctl.start` 重来。

code→方法对照表（含参数形状与 TZ 错误码）见 `findings.md` §33。取方法表最省事的办法是
`llvm-nm -D --defined-only /vendor/lib64/vendor.samsung.hardware.tlc.kg-V2-ndk.so`
（该 so 的 dynsym 没 strip，32 个方法全在）。
