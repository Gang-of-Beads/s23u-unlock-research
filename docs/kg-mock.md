# 用 mitmproxy 假 KG 应答绕过解锁校验（方案记录）

> **最新状态（2026-11-13 夜）：网络层已完全打通，假 enroll 走到最后一个门槛。**
> MITM / pinning 绕过 / 真实协议都已拿下；客户端会真的调 `provisionCert`，
> 但 TZ 对自签证书返回 **264**，需要能过 TZ 的证书或真实签名。详见文末「假 enroll 的推进」。
> 本地 API 手段（`resetRPMB` / `setCheckingState` / `unlockScreen` / `kg30_*`）已确认均无效。
> 实测表明 KG 是**服务器侧**状态：只连网会停在 `Checking`，**登录三星账号**才会把
> `Locked` 推回 `Active`（见 `d2-kg-lock.md`）。因此「让客户端采信 Normal」这条路仍值得试，
> 但现实路径更可能是账号/租户侧放行。下面内容保留但需按新事实复核：
> 入口现在能靠 `resetprop` 显示出来，真正卡住的是 **ABL 的 KG 内容校验（`-5`）**。

目标：把 `knox.kg.state` 从 `Prenormal` 变成 `Normal` 并让系统采信，从而
① 让开发者选项里的 `OEM unlocking` 出现（`shouldBlockCustomRom()` 变 false），
② 让 KMX/开关走完整的三星解锁链路（写 `param`/RPMB，这才是 ABL 认的东西），
**全程不需要三星账号、不需要真实网络**。

## 为什么需要假应答

- `OemUnlockPreferenceController.isAvailable()`：只要 `knox.kg.state` 是 `Prenormal`
  （即 `KnoxGuardManager.shouldBlockCustomRom()` 为真）入口就不显示。
- KG 状态由 `vendor.samsung.hardware.tlc.kg-service`（HAL）＋ `com.samsung.android.kgclient`
  向三星服务器核对后决定；离线时永远停在 `Checking`。
- 已确认 AOSP 的 persistent-data-block 位（`persistent` 分区）**ABL 不认**，
  所以必须让三星那条链路真的跑起来（见 `findings.md` 第 14 条）。

## 已知的服务端线索（来自 `KnoxGuard.apk` 字符串）

- `https://gsl.samsunggsl.com`、`https://stg-gsl.samsunggsl.com`
- `https://pinning-02.secb2b.com/service/umc/leafcert`（证书固定用的叶子证书下发端点，另有 stg 版）
- 客户端里存在状态字面量 `Prenormal` / `Normal` 与字段 `Status` / `result` / `code`
- 真正的 KG 协议实现不在 APK 里（APK 主要是 UI + Firebase），要继续从
  `/vendor/bin/hw/vendor.samsung.hardware.tlc.kg-service` 及其依赖库里挖 URL 和报文结构

## 证书（CA）

`/system` 是 erofs 只读，两条可选：

1. **bind mount 覆盖证书目录**（已验证可行）：
   ```bash
   su -c 'cp -a /system/etc/security/cacerts /data/local/tmp/cacerts'
   # 把 mitmproxy-ca-cert.pem 以 <subject_hash_old>.0 命名放进去
   su -c 'mount --bind /data/local/tmp/cacerts /system/etc/security/cacerts'
   ```
   重启后失效。适合临时实验。
2. **用系统已信任的 CA 签发的叶子**（用户提到的 emudhra 就是这一路）：
   如果手上有一张由系统 store 里已存在的 CA 签发、且能自己持有私钥的证书，
   直接给 mitmproxy 当 `--certs` 用，连 bind mount 都省了，也不怕重启。

## 路由（关键坑）

- 普通 `settings put global http_proxy` 只管 Java 层，KG 的 HAL/原生侧**不走代理**。
- `iptables REDIRECT` + `--mode transparent` 也不行：经过 `adb reverse` 落地是**新建连接**，
  mitmproxy 拿不到 `SO_ORIGINAL_DST`，判定不出目标。
- 可行做法是 **hosts 覆盖 + reverse 模式**：
  1. 把 `/system/etc/hosts` 做成 bind mount，把 KG 域名指向 `127.0.0.1`；
  2. `adb reverse tcp:443 tcp:8443`；
  3. `mitmdump --mode reverse:https://gsl.samsunggsl.com@8443 -s kg_mock.py`
     （每个域名一条 reverse 实例/端口；反向模式不需要原始目标，天然适配这个限制）。

## Mock 策略

- addon 按「主机 + 路径」匹配，返回固定报文：把状态字段写成 `Normal`、成功码写 0；
- 对 `pinning-02…/leafcert` 也要回一份可用的叶子（否则开了 pinning 的客户端会拒连）；
- 其余请求 `flow.resume()` 透传；纯离线时直接返回 200 假体，由我们控制报文。
- 判据：`getprop knox.kg.state` → `Normal` 且能稳定住（多次轮询不变回 `Prenormal`）。

## 逆向到的接口（jadx `KnoxGuard.apk`）

- 查找（lookup）：`https://gsl.samsunggsl.com/gksl/v1/lookup/device/kg`
  （`t4/a.java` 用 `b + "/gksl/v1/lookup/" + "device/" + "kg"` 拼；stg 域为 `stg-gsl.samsunggsl.com`）
  请求体 `LookupServiceRequest` 字段：`apSerialProp`(=`ro.boot.kg.ap`)、`countryIso`、`csc`、
  `mcc`（取自 SIM/网络运营商前 3 位）。
- 响应模型 `LookupServiceResponse`：`clientDownloadUrl[]`、`kslUrl[]`、
  `serviceInfo{profileId, registered, serviceIdentifier, serviceUrl[]}`；
  `registered` 缺省按 `false` 处理。
- 成功后客户端会去 `<KG_UMC_CDN_URL>/kgc20/KGC20.apk`（或 `/kgc20/lite/KGC20_lite.apk`）下载，
  并走 `models/enrollment`、`models/hotpprovisioning` 的流程。
- 状态枚举（`p4/c.java`）：`Prenormal(0) / Checking(1) / Active(2) / Locked(3) / Completed(4) / Error(5)`；
  `knox.kg.state` 里看到的 `Normal` 由 TrustZone（`KGTA_getKgState`）给出，客户端主要做镜像与触发。
- 证书固定：`https://pinning-02.secb2b.com/service/umc/leafcert`（有 stg 版），
  客户端会自行校验叶子，mock 时必须给这个端点也回可用的叶子，或让它继续连真站。

## 关键不确定性

`knox.kg.state` 是 TZ 权威状态的镜像；把 lookup 应答 mock 成 `registered=true` 能骗过 Java 侧，
但**TZ 是否因此把 Prenormal 改成 Normal**还没验证。若 TZ 不认，mock 只能让 UI/框架以为正常，
ABL 仍然不买账——那就得回到 `param` 直写。

## 待补（按优先级）

- [x] 提取 URL/路径/字段（见上；HAL 本身只调 TZ 的 `KGTA_*`，不联网）
- [ ] **找到能稳定触发 lookup 的入口**（当前最大卡点：广播只走 HANDLE_SERVICE_INTENT 就停）
- [ ] 记录一次真实报文（有网时先做 passthrough，把 flows 存下来当模板）
- [ ] 确认状态是否也会被 TrustZone/RPMB 二次校验（若会，则 mock 只能骗过 Android 侧，
      需要再配合 `param` 直写）
- [ ] 落地成 `scripts/kg_mock.py` + `scripts/kg_mock_setup.sh`（hosts bind、reverse、启动 mitm）

## 相关

- 入口/开关/限制的完整判定链：`findings.md` 第 14 条
- 清 `no_oem_unlock` 限制的小工具：`scripts/build_helper.sh` + `scripts/helpers/Unrestrict.java`

## HAL 侧（已确认不联网）

`/vendor/bin/hw/vendor.samsung.hardware.tlc.kg-service` 只做 TZ 转发，符号全是
`KGTA_getKgState` / `KGTA_getKgPolicy` / `KGTA_getNonce` / `KGTA_getHotpChallengeCode` /
`KGTA_getHdMStatus` 之类；没有 URL、没有 socket。所以网络只发生在 Java 侧（`KnoxGuard.apk`），
mock 点在它，不在 HAL。

## 相关脚本（占位，待实现）

- `scripts/kg_mock.py`：mitmproxy addon，按 host+path 返回假报文（lookup→registered=true，
  leafcert→固定叶子），其余透传
- `scripts/kg_mock_setup.sh`：hosts bind mount + `adb reverse` + 起 mitm

## 实测（2026-11-12）：通路已通，卡在触发与 pinning

- 环境：gnirehtet 提供连通性；`adb reverse tcp:8443 tcp:8443`；
  `iptables -t nat -A OUTPUT -p tcp --dport 443 -j REDIRECT --to-port 8443`（**不带 `-d`**，
  全局劫持最简单，且 IPv6 走不通时不影响）；`mitmdump --mode reverse:https://gsl.samsunggsl.com@8443 -s scripts/kg_mock.py`。
- 用三星浏览器访问 `https://gsl.samsunggsl.com/gksl/v1/lookup/device/kg` 验证：请求确实被劫持、
  mock 返回 200 与预期 JSON（`clientDownloadUrl`/`kslUrl`/`serviceInfo.registered=true`）。
- **证书**：mitm CA 以 bind mount 覆盖 `/system/etc/security/cacerts` 后，普通 App（浏览器）接受；
  但 KG 客户端对 `pinning-02.secb2b.com` **做 pinning**，握手直接
  `tls alert certificate unknown`。临时办法是对它的真实 IP 加 `-j RETURN` 放过（实测已加），
  长期办法是给这个端点回来自信任根的叶子（emudhra 那一路）。
- **卡点：触发。** `am broadcast` `BOOT_COMPLETED` / `LOCKED_BOOT_COMPLETED` / `KNOXGUARD_ENROLLED`
  只让 `KGEventService` 走一次 `HANDLE_SERVICE_INTENT` 就 STOP，不会发 lookup；
  客户端只在内部事件/闹钟里查。已知一次真实 lookup 出现在状态被改成 `Checking` 后由自身流程发起
  （当时报 `Expected BEGIN_OBJECT but was STRING`，说明 mock 的 body 还得按真实结构校准）。
- 顺带：`cmd netd`/`cmd dnsresolver` 在 Android 16 上不可用，DNS 劫持只能靠 iptables DNAT 到自建
  resolver；`/system/etc/hosts` 改了也没意义（resolver 会缓存）。

## 另一个思路：hook kgclient / kmx，直接让「解锁成功」

结论先说：**hook 能解决「看起来允许解锁」，但决定不了 ABL 认不认**，因为写锁状态的不是
kgclient，而是 TrustZone（由 KMX 那条链路驱动）。分三层看：

| 层 | 谁负责 | hook 有用吗 |
| --- | --- | --- |
| 入口是否显示 | `KnoxGuardManager.shouldBlockCustomRom()`（读 KG 状态） | 有用，但 `resetprop knox.kg.state Normal` 已等价且更便宜 |
| 开关是否可点 | `UserManager.hasUserRestriction("no_oem_unlock")` | 有用，但 `app_process` 调 `IUserManager` 已等价 |
| **写 param/RPMB** | 开关 → `OemLockManager.setOemUnlockAllowedByUser` + 广播给 `com.samsung.android.kmxservice`（`CHANGE_OEM_UNLOCK_ALLOWED`）→ KG/TrustChain（TZ） | **hook 在这里才真正有价值**：这台没有 OEM lock HAL，框架只写了 AOSP 的 persistent block 位，而 ABL 不认 |

所以要 hook 就该 hook **KMX 的 `EVENT_CHANGE_OEM_UNLOCK_ALLOWED` 处理**（或它调用的 TZ 接口），
目标是让它真的走到 `KGTA_setKgInfo`，而不是只写 persistent 位。风险：KMX 很可能需要 HOTP/nonce
（`KGTA_getHotpChallengeCode`）与服务器下发的数据，那样又会绕回 mock。

### 可行的 hook 机制（无 Xposed）

`/system` 是 erofs 只读，但没有阻挡：把 APK 复制出来、patch、`mount --bind` 覆盖回原位即可
（跟证书目录同一手法，重启失效）。工具：`brew install apktool` + `apksigner`。

候选顺序：

1. `KmxService.apk` — 在 `EVENT_CHANGE_OEM_UNLOCK_ALLOWED` 处理里打日志/直调 TZ（优先，信息量最大）
2. `KnoxGuard.apk` — 直接返回 `Normal`，省掉触发与云端（但它只为前两层服务）
3. `framework`/`services` 的 `OemLockService.PersistentDataBlockLock` — 意义不大（已证 ABL 不读）

### 判定 hook 是否成功的硬指标

不看 UI，只看这两条：

- `param` 分区哈希在拨动开关后**发生变化**（当前不变 → 说明没走到 TZ）
- 或 `ro.boot.kg` / `knox.kg.state` 在重启后仍为非 Prenormal

两条都不动就说明 hook 没触及 TZ 层，仍要回到「假应答 + 真 HOTP」或 param 直写。

## 为什么「hook 一下就当成功」不够 —— ABL/TZ 侧证据

1. **这台机器确实没有 OEM lock HAL**：`service list` 只有 AOSP 的 `oem_lock`，
   `/vendor/etc/init` 与 `/vendor/bin/hw` 里都没有 oemlock 相关项。框架只能走
   `PersistentDataBlockLock`。
2. `persistent` 分区里**确实有** AOSP PDP 结构（偏移 `0x20` 处是 magic `0x19901873`），
   我们拨开关后该分区哈希变化（`28997bf…` → `508b5be…`），说明 AOSP 位真的写进去了；
   但 ABL 带着它仍然只显示 `Downloading...`，长按音量上无反应 → **ABL 不读这个位**。
3. ABL 侧：`BL_*.tar.md5` 里的 `abl.elf` 不是纯文本，`0x102a` 处是 UEFI Firmware Volume 头
   （`_FVH`），模块按 EFI 压缩段存放，所以要读解锁判定逻辑需要 UEFITool 先解压（待办）。
4. TZ 侧：KG 状态是 TZ 权威，客户端通过 `KGTA_getHotpChallengeCode` 拿 challenge、
   服务器下发 **HOTP**，再 `KGTA_setKgInfo` 交给 TA 校验。HOTP 由 TA 内共享密钥校验，
   **没法凭空伪造**——但**可以重放**：同一 challenge 在同一次开机内大概率仍然有效。

因此：

- hook（改 kgclient/kmx）只能伪造「Android 侧认为 Normal」，TZ 仍不动；
- 想真正过关，需要「真报文一次」——把 HOTP 拿到手，之后离线重放（或用它换出
  `setKgInfo` 成功，让 TZ 把 KG 置 Normal 并写 `param`）。

### 下一步（最省事顺序）

1. 用真网络 + mitm **passthrough**（对 pinning 域名放行）抓一次完整交互，存 flows 当模板；
2. 从 flows 里取 HOTP/challenge 与报文结构，写成可重放的 mock；
3. 重放成功后立刻拨开关，检查 `param` 哈希是否变化（唯一硬指标）。

（三星账号只在服务器要求绑定/登记时才是必需的；先看抓到的报文到底要不要求。）

## 触发尝试记录（都没能让客户端发 lookup）

已试过、全部无效（服务起来后立刻 `HANDLE_SERVICE_INTENT` → `getTAState=Checking` → `STOP`）：

- `am broadcast -a android.intent.action.BOOT_COMPLETED -n …/.receiver.SystemIntentReceiver`
- `LOCKED_BOOT_COMPLETED` / `KNOXGUARD_ENROLLED` / `MANUAL_UNLOCK` / `TIME_SET`
- `com.sec.android.app.setupwizard.SETUPWIZARD_COMPLETE`（含 sec 前缀版本）
- `am startservice …/.events.KGEventService`
- `am start -n …/.ui.activities.browserenrollment.LaunchActivity`（该 Activity 未导出，
  直接启动报 `Error type 3`；`smdm://` scheme 实际落到 `com.sec.enterprise.knox.cloudmdm.smdms`）
- `monkey -p com.samsung.android.kgclient 1`（无 launcher activity）
- 改 `/data/data/com.samsung.android.kgclient/shared_prefs/KG_shared_pref.xml`：
  `isBootAfterReset=true`、`start_on_network_availability=true` 后再触发，仍无效

唯一确认有效的是**真开机**（23:10 那次 lookup 就是开机后自发发的），但 iptables 规则重启即失效，
root 又要等 60 秒 uptime gate，赶不上开机窗口。

下次尝试方向（择一）：

1. 让环境扛过重启：把 iptables/reverse/mitm 做成开机后自动执行（宿主机侧循环等设备上线，
   拿到 root 后立即补规则，再 `am force-stop` + 触发一次）
2. 直接 hook `KGEventService`/`KGWorkerThread` 里那个 `HANDLE_SERVICE_INTENT` 分支，强制走到 lookup
3. 读 `s5/d` 与 `m4/c` 的消息表，找出真正触发 lookup 的消息码，用 `am` 打不进去就 hook 补一条

## ABL 反汇编证据（UEFITool 解 FV 后取字符串）

处理方法：`abl.elf` 是 ELF，段 1（`0x1000`，长度 `0x252000`）里 `0x1000` 起就是 UEFI FV
（`0x1028` 处 `_FVH`）。用 `UEFIExtract`（LongSoft/UEFITool A76, universal mac 版）解出
`Odin` 与 `LinuxLoader` 两个模块的 PE32 body，然后取字符串。

关键串（`LinuxLoader` 和 `Odin` 两个模块里都有）：

- `All binaries are not allowed to be flashed due to KG locked`
- `[KG]QseecomStartApp (tz_kg) call success status=%d, KGAppId=%d`、`[KG]QseecomShutdownApp (tz_kg)`
- `SetKGFuse`、`StoreRPMBToBK`
- `GetUnlockCount`、`tima_get_warranty_vio_fuse`

读出来的结论：

1. **ABL 不读 persistent data block**（整个 payload 里没有 PDP 相关串），只跟 TZ 的 `tz_kg` 通信，
   状态落在 **RPMB**（`StoreRPMBToBK`）。这解释了为什么我们写 PDP 位 ABL 毫无反应。
2. **`-5` 大概率就是 KG 导致的**：`All binaries are not allowed to be flashed due to KG locked`
   在 Odin 模块里就是刷写拒绝的分支。也就是说 **KG 一旦变 Normal，即使未解锁，
   改过的 `init_boot` 也可能被接受** —— 这条比「解锁」本身更容易先拿到（持久 root）。
3. 因此优先级调整：**先想办法让 TZ 的 KG 变 Normal**，其次才是解锁。

### 工具链（可复用）

```bash
dd if=abl.elf of=abl_fv.bin bs=1 skip=$((0x1000)) count=$((0x252000))
UEFIExtract abl_fv.bin            # 产物在 abl_fv.bin.dump/.../PE32 image section/body.bin
strings -a body.bin | grep -iE 'KG|unlock|RPMB'
```

## 绕过 app，直接调 KG HAL（已打通调用通路）

KG 的 TZ 接口是 AIDL HAL：服务名
`vendor.samsung.hardware.tlc.kg.ISehKg/default`，**descriptor 是
`vendor.samsung.hardware.tlc.kg.ISehKg`（不带 `/default`）**。

坑：`service call vendor.samsung.hardware.tlc.kg.ISehKg/default <code>` 一律回
`ENODATA(-61)`，因为 `service call` 用服务名当 interface token，和 descriptor 对不上。
必须自己发 binder：`data.writeInterfaceToken("vendor.samsung.hardware.tlc.kg.ISehKg")`。

可用工具：`/data/local/tmp/kgcall.jar`（源码在会话里，逻辑是 `app_process` + 反射
`ServiceManager.getService` + 逐 code `transact`）：

```bash
su -c 'CLASSPATH=/data/local/tmp/kgcall.jar app_process /system/bin dev.pi.kgcall.Main'
```

现状：

- 修复 token 后能拿到**真实应答**（`code 7` 返回 int 1、`code 18` 返回 int 0 等），
  不再是 ENODATA；
- 但**方法序号没确定**：HAL 是 stripped aarch64 ELF（`llvm-objdump` 无符号），
  只能靠 code × 参数组合盲试，而结果随 TZ 状态漂移，噪声大；
- 客户端 AIDL stub 类**不在** `KnoxGuard.apk` 里（`vendor.samsung.hardware.tlc.kg.ISehKg$Stub`
  ClassNotFound），所以没法直接走生成的 Proxy。

待办：从 HAL 的 `BnSehKg::onTransact` 反汇编出 code→方法映射（stripped 需要手工定位 switch），
之后就能直接 `getKgState()` / `setKgInfo(state, hotp)`，把「客户端触发」这个卡点彻底绕开。

### 探测现状（2026-11-13）

- 源码路径线索：`/vendor/bin/hw/vendor.samsung.hardware.tlc.kg-service` 里留有
  `vendor/samsung/interfaces/tlc/kg/2.0/aidl/default/service.cpp`，即接口是 Samsung 私有 2.0。
- 二进制 stripped，但有 `.gnu_debugdata`（xz 压缩的迷你符号表）；解出来后只有 87 个符号，
  仅覆盖 `kgta_ctx`/`create_comm_ctx` 等自身代码，**没有 `BnSehKg::onTransact`**，
  所以拿不到现成的 code→方法映射。
- 盲探结果：`code 12`、`code 13`（带任意参数）能稳定返回 void 成功；其余 code 在参数形状不对时
  一律 `ServiceSpecificException(-1000)`，而某些时刻 `code 7` 能返回 `int 1`。
  说明大多数方法需要非平凡参数（byte[]/结构）且依赖 TZ 会话已建立，噪声大。

### 继续的正确做法

1. 反汇编 `onTransact`：以 `.dynstr` 里的符号
   `_ZN4aidl6vendor7samsung8hardware3tlc2kg6ISehKg10descriptorE` 的 GOT 引用为锚点，
   定位比较分支，读出 switch 的 case 常量 → 得到 code 表；
2. 或直接找 Samsung AIDL 2.0 的定义（`vendor/samsung/interfaces/tlc/kg/2.0/aidl/*.aidl`）：
   方法顺序即 transaction code，参数类型也在里面。

### onTransact 映射（拿到一半）

关键突破：HAL 的真正 stub 在 **`/vendor/lib64/vendor.samsung.hardware.tlc.kg-V2-ndk.so`** 里
（`kg-service` 只做 TZ 转发）。该 so 带 `.gnu_debugdata`，解压后能拿到
`_aidl_..._ISehKg_onTransact` 符号，反汇编即得：

```
7160: sub  w8, w22, #0x1     ; v22 = code
7164: cmp  w8, #0x1b         ; 28 个方法
7168: b.hi default
7170: adr  x9, 0x4ad0        ; 跳转表（28 × uint16，target = 0x7184 + ent*4）
```

每个 case 调用的接口 vtable 槽位 `slot` 与 code 固定关系：**`slot = code + 3`**。
已解出的 shape（读参类型）：

| code | 读参 | 备注 |
| --- | --- | --- |
| 1–5, 7, 8, 11, 17, 25, 28 | `Int32` | |
| 6, 10, 13, 14, 26 | `ByteArray` ×2 | |
| 12, 15, 16 | `ByteArray` | |
| 18–24, 27 | 无入参（纯出参） | 18/19 返回 void |

行为观测（会随 TZ 会话状态漂移，噪声大）：
`code 5` 曾返回 24 字节全零 blob（疑似 `getKgId`/`getNonce` 一类）、`code 7` 曾稳定返回
`int 3`（状态枚举）、`code 12/18` 稳定 void 成功。多数 code 在 TZ 上下文未建立时回
`ServiceSpecificException(-1000)`。

判断：调用前需要走一次会话初始化（`getNonce` → `setClientData` 之类），否则拿不到数据。
后续应先把 `slot = code + 3` 与 kg-service 里各 override 引用的 `KGTA_*` 函数对上
（override 里有 `KGTA_getKgState failed` 这类日志串可作指纹），再按顺序建会话。

产物：`kgndk.so` 已拉到本机 `/tmp/kgndk.so`、设备 `/data/local/tmp/kgndk.so`；
`onTransact` 反汇编在 `/tmp/ot.dis`。

### HAL override 顺序（KGTA 指纹对齐）

`kg-service` 里每个 override 都带 `KGTA_xxx failed` 日志串，按引用地址排序即可得到实现顺序
（`0x5db8`–`0x7e38`）：

| # | KGTA 调用 | # | KGTA 调用 |
| --- | --- | --- | --- |
| 1 | unlockScreen | 14 | generateHotpDhRequest |
| 2 | lockScreen | 15 | verifyHotpDhChallengeCode |
| 3 | getLockActionId | 16 | verifyHotpSecret |
| 4 | getLockActionData | 17 | verifyCompleteToken |
| 5 | getKgState | 18 | verifyHotpPin |
| 6 | getClientData | 19 | verifyRegistrationInfo |
| 7 | getKgId | 20 | verifyKgPolicy |
| 8 | getHdmStatus | 21 | getKgPolicy |
| 9 | verifyKgRot | 22 | resetKgInfo |
| 10 | getNonce | 23 | getTAInfo |
| 11 | getHotpChallengeCode | 24–26 | provisionCert / verifySfPolicy / readSfPolicy |
| 12 | setUserCheckingState | | |
| 13 | setClientData | | |

**与 onTransact 的 code 对齐**：形状交叉验证（code 5 返回 24 字节 blob → `getClientData`；
code 7 返回 int → `getHdmStatus`；code 12 收 ByteArray、返回 void → `setClientData`）
指向 **code = 表内序号 − 1**（即 vtable 前面有 2 个非方法槽）。据此：

- `getKgState` ≈ **code 4 或 5**（都收 Int32，需实测区分）
- `setClientData` ≈ **code 12**（ByteArray → void，已能调通）
- `resetKgInfo` ≈ code 21、`getNonce` ≈ code 9、`getHotpChallengeCode` ≈ code 10
- **没有 `setKgInfo`**：状态是经 `setClientData` / `verifyCompleteToken` / `resetKgInfo` 间接改的

下一步：用 `getNonce`(9) → `getHotpChallengeCode`(10) → `setClientData`(12) 走一遍会话，
只读不写地观察 TZ 返回，再决定重放 HOTP 的时机。

### 实测映射（2026-11-13，结论：index = code + 1）

用 `/data/local/tmp/kgcall.jar` 逐 code 试参，得到可用样本与返回：

| code | 参数形状 | 结果 | 对应方法（按 index−1） |
| --- | --- | --- | --- |
| 5 | 任意 1 参 | 返回 24 字节 blob（status + 0x18 + 24B） | `getClientData` |
| 7 | 任意 | 返回 `int 3` | `getHdmStatus` |
| 9 | 任意 | 返回 16 字节 nonce（status + 0x10 + 0x20 + 16B） | `getNonce` |
| 12 | `int` + `byte[]` | void 成功 | `setClientData` |
| 13 / 15 / 16 / 18 | `byte[]` | void 成功 | `setUserCheckingState` / `verifyHotpSecret` / `verifyCompleteToken` / `verifyHotpPin` |
| 6 | `int` + `byte[]` ×2 | KGTA 状态 **520** | `getKgId` |
| 4 | 需 int（裸 int 回 -1000） | — | `getKgState` |
| 10 | 需 ≥2 参（各种组合仍 `Not enough data`） | — | `getHotpChallengeCode` |

三个关键坑：

1. **不能用 `Parcel.marshall()`**：部分方法（如 code 10）的 reply 带 fd，`marshall()` 会抛
   `ParcelFormatException`，应改成 `readException()` 后按 `dataAvail()` 循环 `readInt()`。
2. 参数缺失时 HAL 常回 `Bad file descriptor` 并把客户端 SIGKILL（表现为 `Killed`），不是崩溃。
3. HAL 是 `disabled oneshot`，用前 `setprop ctl.start kgtaserv` 拉起，否则 binder 无响应。

会话顺序应照 index 走：`getNonce(9)` → `getHotpChallengeCode(10)` → `setClientData(12)`；
其中 10 的形状还没定，是当前唯一挡住流程的格子。

### code 10 (`getHotpChallengeCode`) 的形状与「炸 HAL」

从 `onTransact` 反汇编读出的真实入参（`0x7378` 起）：先是两次 `AParcel_readByteArray`
（x29-0x20、x29-0x38），再读一个 int（sp+0x30），然后带两个 out（sp+0x30、sp+0x8）调接口。
即形状是 **`(byte[] a, byte[] b, int)`**，我们之前试的 `int, ba, ba` 顺序是错的。

修正顺序后仍然 **SIGKILL**。原因查明：不是参数问题，而是**调用会把 kgtaserv 打死**
——调用后 `init.svc.kgtaserv` 仍显示 `running`，但 `ps` 里没有进程（oneshot 不会自动重启），
客户端因为 binder 代理失效，在崩溃处理器里又触发 `Bad file descriptor`，所以只剩一句 `Killed`
没有堆栈。

推论：`getHotpChallengeCode` 需要先建立 TZ 会话（ctx/comm 已初始化、clientData 已灌），
裸调会让 HAL abort。正确顺序应先 `getTAInfo`(23) / `getClientData`(5) / `setClientData`(12)
把上下文建起来，再调 10。

恢复：`setprop ctl.start kgtaserv`。

---

# 2026-11-13 实跑记录（关键发现，务必先读）

结论：**还没有跑通，但把整条 pinning 链路完整挖出来了**，卡在最后一步（见“卡点”）。

## 1) KG 的 pinning 是两段式 + MPS

- `w4.a`（MPS 通道的 TrustManager）从 APK 资产 `assets/MASTER_PINNING_SERVER_CERT_{PROD|STAGE}.PEM`
  读一张**钉死的锚证书**，用它去校验 MPS 端点。所以 MPS **本身不能 MITM**，除非换掉这张资产。
- `w4.d.e()` 用 `w4.a` 拉 `https://pinning-02.secb2b.com/service/umc/leafcert`，
  响应是 `{"data":[{"CA":[<PEM...>],"URL":["host:443",...]}]}`，写进 `mpsCertResponse` 偏好项。
- `w4.b.checkServerTrusted`：先用**系统默认** TM 验链，再把**链的第一个证书的公钥**与 MPS 给的
  `CA` 列表逐个比公钥，相同才放行。所以 **MITM 必须同时满足两件事**：
  ① 证书能过系统信任（锚进系统库）；② 叶子公钥必须等于 pin 列表里的某个证书公钥。
- mitmproxy 给叶子签的证书**公钥与它自己的 CA 完全相同**（实测 md5 一致），
  所以只要把 pin 列表换成 mitm 的 CA，②就满足。

## 2) Android 16 的 CA 注入路径变了

`/system/etc/security/cacerts` 是 dm-63 的独立挂载，但**Conscrypt 实际读的是
`/apex/com.android.conscrypt/cacerts`**。而且 apex 在 **每个 mount namespace** 里各有一份，
在 shell 里 bind 对 App 无效，必须注入到 zygote 的 namespace：

```bash
mkdir -p /data/local/tmp/apexcerts
cp -a /apex/com.android.conscrypt/cacerts/. /data/local/tmp/apexcerts/
cp /data/local/tmp/<hash>.0 /data/local/tmp/apexcerts/
for p in $(pgrep -f zygote); do
  nsenter -t $p -m -- mount --bind /data/local/tmp/apexcerts /apex/com.android.conscrypt/cacerts
done
```
（`mount -o remount,rw /apex/com.android.conscrypt` 会报 read-only，只能用 bind。）

## 3) 替换 APK 资产换锚证书（走通了）

`/system` 其实是 rw，直接覆盖即可（**必须 `chown root:root` + `chmod 644` + `chcon system_file`**，
否则 ART 报 `Writable dex file ... is not allowed` 直接崩）。bind mount 一个来自 /data 的文件会
被判为可写 dex，同样崩。

重建 zip 时 **`resources.arsc` 必须保持 STORED 且 4 字节对齐**，否则 `Resources` 为 null、
`handleBindApplication` 直接 NPE。参考脚本见本次会话的 python 片段。

替换后 MPS 通道立刻变成可以 MITM（我方 CA 被接受）。

## 4) 卡点

MITM MPS 成功、CA 也成功注入了系统库（默认 TM 验链已通过），但最后一步
公钥比对仍然报 `[pinning]This server does not have the correct certificate`。
现象：`certsTrusted.isEmpty() : true` 随后出现、`mpsCertResponse` 偏好项始终没被写入，
推测是 `w4.d.d()` 把 `<string>` 里的 PEM 解析成 `null` 或者 URL 匹配不到（日志里被查找的 URL 打出来是
截断的 `https:af:443`），于是落到 `Pinning data is empty` 分支。

### 已排除的假设（实测）

- **PEM 解析没问题**：写了 `Pem.java`（`android.util.Base64.decode(s.trim(), 0)` +
  `CertificateFactory`，与 `w4.d.d()` 同路径），单行和带换行的 PEM 都 `PARSE_OK`。
- **公钥本来就相同**：mitmproxy 叶子的 SPKI DER md5 == CA 的 SPKI DER md5（都是 `0ccd9301…`），
  所以"叶子公钥 vs pin 列表公钥"应当相等。

### 仍然没解释的现象

日志顺序是「先 `does not have the correct certificate`，紧接着 `Pinning data is empty`」。
后者是因为前者抛的 `w4.e` 会把 `mpsCertResponse` 清空。也就是说：**第一条请求确实读到了
我们种进去的 pin 列表并走到了公钥比对，但比对仍然失败**，之后列表被清空。

另外手工写进 `KG_shared_pref.xml` 的 `mpsCertResponse` 在跑一次后就消失（App 用内存值覆盖）。

下一步二选一：
1. 继续逐行验证 `w4.b.checkServerTrusted`（`listA.get(0)` 到底拿到链里哪张、Conscrypt 返回顺序）；
2. 直接用 apktool 改 smali，让 `w4.b.checkServerTrusted` 直接 `return`（我们已经会改 APK 并保住
   dalvik 能加载的属性，这条路成本反而更低）。

## 5) 现场残留（重启全失效）

- iptables：MPS `13.35.172.47` 与 GSL `99.80.45.82` / `52.211.134.225` 的 443 → 8443/8444；
- `adb reverse tcp:8443/8444`；mitmdump `--set ssl_insecure=true`（MPS 是三星内网自签链）；
- `/apex/com.android.conscrypt/cacerts` 的 zygote 级 bind（144 项）；
- `/system/priv-app/KnoxGuard/KnoxGuard.apk` 已被覆盖成改过资产的版本（原版备份在
  `/data/local/tmp` 之外需要自己留一份）。
- 设备 KG 仍为 `Active`，没有变差。

---

# 2026-11-13 傍晚：MITM 完全打通（但 KG 仍未变 Normal）

## 结论

**网络层已经全部拿下**：可以完整拦截、读取、伪造 KG 的全部请求。剩下的是**协议语义**——
KG 的真状态由 TZ 决定，客户端只有在拿到服务端的相应应答后才会调 HAL 去改，目前还没伪造出那份应答。

## 打通过程（按依赖顺序，缺一不可）

1. **替换 APK 里钉死的 MPS 锚证书**。注意：App 已被自更新到 `/data/app/.../base.apk`（3.2.91），
   **改 `/system/priv-app` 那份没用**；自更新包本体留在
   `/data/data/com.samsung.android.kgclient/app_KGAPKDIR/kgagentselfupdate.apk`，直接用它改最省事。
2. **CA 注入到 `/apex/com.android.conscrypt/cacerts`（zygote namespace）**，见上一节。
3. 因为 MPS 通道的 `w4.a` 和通用 `w4.b.checkServerTrusted` 都还有坑，最终用 apktool 改 smali：
   - `w4/a.checkServerTrusted` 与 `w4/b.checkServerTrusted` 方法体开头直接 `return-void`；
   - `w4/d.c()` 去掉「pin 列表为空就抛 `w4.c`」的分支，改为永远返回 TrustManager。
   这样 pinning 整层被绕开（日志变成 `certsTrusted.isEmpty() : false` 正常放行）。
4. 部署要点：目标 APK 路径改完要 `chown system:system` + `chmod 644` + `chcon apk_data_file`，
   然后 `cmd package compile -f -m speed`，再 force-stop；否则跑的是旧 oat。
   （`/system` 是 ro，APK 只能 bind mount，且必须 644，否则 ART 报 `Writable dex file`。）

## 抓到的真实协议（这是本轮最大产出）

工具链门槛过了以后，把整条链抓完了：

| 请求 | 真实响应 |
| --- | --- |
| `POST https://gsl.samsunggsl.com/gksl/v1/lookup/device/kg` | 200，`serviceInfo.registered = **false**`（本机未登记进任何 KG 租户），`serviceUrl = eu-gslu` |
| `POST https://eu-gslu.samsunggsl.com/af/v1/sal/devices/enhanced/getKGStatus` | **204 No Content**（无状态变更） |
| 另外还会打 `.../getPolicy`、`.../report` | 见下列模型 |

lookup 请求体就是识别信息（`apSerial`、`imeiHash`、`serialHash`、`csc`、`countryIso`、`mcc`），
不带任何密钥，可以直接用 curl 重放验证。

客户端解析用的模型（jadx）：`com.samsung.android.kgclient.models.kgstatus.KGStatusResponse`
（字段 `action` / `certs` / `regInfo` + `regInfoSignature` / `lockInfo` / `completeMsg` / `policyRequired` …）、
`LockInfo`（`companyName`/`emailAddress`/`message`/`phoneNumber`）。
`registered=true` 且带 `regInfo`+签名时会走完整 **enrollment**，需要连证书下发一起伪造。

## 顺手验证的两件事

- `KnoxGuardManager.getTAState()` 现在返回 `2`（Active），但
  **`shouldBlockCustomRom()` 仍返回 `true`**——所以"入口可见"和"允许 custom"是两码事。
- 借此再刷一次 patched `init_boot`：**依旧 `-5`**。也就是说 KG 侧只要不是它认定的放行态，
  ABL 就继续拒。跟 prop 上的 `Active` 没直接关系。

## 因此真正要伪造的东西

不是 "让 prop 变 Normal"，而是让客户端走完 `getKGStatus` 的语义并调 HAL 把 TZ 状态推到放行态。
两条现实路径：

1. 伪造 `KGStatusResponse`（`action`/`lockInfo`/`certs`）让客户端执行解锁动作；
2. 直接调 framework 的 `KnoxGuardManager`（`setCheckingState()` / `unlockScreen()` /
   `kg30_*` 系列）看能否把 TZ 推过去——已写好反射工具（`/tmp/KG2.java` 那套），可继续试。

## 现场（重启即失效）

- 全量 iptables 影子：gsl / eu-gslu / pinning-02 的 IP:443 → 8443/8444/8445（含 adb reverse）；
- mitmdump 三实例（`--set ssl_insecure=true`）；
- consscrypt apex CA（zygote namespace bind，144 项）；
- `/data/app/.../kgclient.../base.apk` 换成打过补丁的 3.2.91（原包在 `app_KGAPKDIR/kgagentselfupdate.apk`）；
- KG 仍 `Active`，未变差。

## 直接调 framework（路径 ②）试过了

`com.samsung.android.knoxguard.KnoxGuardManager`（system_server 的 KG 前端）只接受
**调用方 uid == com.samsung.android.kgclient**，否则抛
`SecurityException: caller should be com.samsung.android.kgclient`。

绕过办法：`app_process` 里先 `android.system.Os.setgid/setuid(10096)` 再调，就放行了
（`/tmp/KG5.java`、`/tmp/KG6.java`）。可用的方法：

| 方法 | 结果 |
| --- | --- |
| `getTAState()` | `2`（Active） |
| `shouldBlockCustomRom()` | `true` |
| `setCheckingState()` | `-1`（失败） |
| `kg30_setCheckingState()` | `null`（KG30 老接口，本机走 v2 HAL，不适用） |
| `unlockScreen()` | `0`，但状态仍是 `2` |
| `kg30_bindToLockScreen()` | `false` |

结论：能无权限障碍地摸到 HAL，但**这些老接口不足以把 TZ 推成放行态**——还是要靠服务端驱动的
完整 enrollment / policy 流程（路径 ①），或伪造 `KGStatusResponse`。

也顺带在 ABL 里定位了 `-5` 那段的代码（`Odin` body 里 `0x6c6cc` → 打印
`All binaries are not allowed to be flashed due to KG locked`，进入该分支前读 `[x19+0x8]`），
但真正的判定在上游函数里，尚未追完。

## ABL 里 `-5` 的追查结果（静态）

在 `Odin` 的 body 里定位到了相关结构，但**没找到能直接改的开关**：

- 全局 KG 状态结构在 `0xd9e48`（`GetKGStatus` 的返回值存在 `+0x64`，即 `0xd9eac`）；
  全二进制只有一处读它：`0x6c4f8`（`ldr w8,[x8,#0xeac]`）。
- 该处是一个 **跳转表**（表在 `0xcc0cf`，`adr x10,0x6c51c` + `br x10`），按 KG 状态选不同文案：
  - 0/2/5 → `Custom Binary(%a) Blocked due to remaining installment balance`
  - 3 → `[SD] Binary authenticate fail due to NoSignInfo`
  - >5 → `Custom Binary(%a) Blocked due to Unknown KG status`
- 我们实际撞到的是 `0x6c6cc` 那条：`All binaries are not allowed to be flashed due to KG locked`
  （由外层 switch 的某个 case 直接跳进去）。
- 判定条件不在这个打印函数里：进入前读的是 `[x19+0x8]`（`cmp #1` → `bl 0x6c800`），
  也就是 `-5` 由**上游**决定，打印函数只负责选文案。

**结论**：ABL 侧没有可以「写一个字节就放行」的软开关；它读的是 TZ 里 KG 的真实状态。
所以还是要让 TZ 侧进入放行态 —— 也就是客户端拿到服务端"已放行/已登记"的应答后去调 HAL。

## 由此收敛出的判断

真实 lookup 返回 `registered:false`，说明**这台机没被登记进任何 KG 租户**；
客户端因此拿不到 policy，TZ 就一直停在 ABL 眼里的"locked"（prop 上的 `Active` 只是客户端侧的说法，
与 TZ 判定不一致，也解释了为什么 `-5` 与 `knox.kg.state` 无关）。

要真正推进，只有两条：

1. **真实登记**：把机器加进某个 KG 租户（`registered:true`），走真 enroll —— 这条最稳；
2. **假 enroll**：mock `registered:true` 并伪造 `regInfo` + 签名（`getKGStatus` 的
   `KGStatusResponse`），难点是签名要能过 KG 的 provision 证书校验。

## 假 enroll 的推进（本地绕过尝试）

把 mock 补成完整链路后，客户端确实走完了整条流程：

```
lookup(registered:true) → HEAD kgc20 → getKGStatus(200+certs/regInfo) →
CertProvisionProcessor@provision → KGServiceManager@provisionCert → TZ
```

`getTAInfo` 打印 `CertProvisioned`，说明 TZ 里证书状态被查询到了；随后：

- `provisionCert(enrollCrt, provisionCrt, policySigningCrt, blSigningCrt)` → TZ 返回 **264**，
  HAL 打 `KGTA_provisionCert failed`，客户端 `@provisionCert - res = -1`。
- 自行生成的证书（RSA2048 自签、EC P-256 自签都试过）**都被 264 拒**。
  所以 TZ 对这几张证书有格式/链上的硬要求（大概率要能链到三星内部根），
  不是随便塞四张自签就能过。

结论：假 enroll 的下一个门槛是 **拿到能过 TZ 的证书**（真机的 enroll/provision cert 由服务端下发，
本机未登记所以拿不到）。要继续推进，需要：

1. 在别的已登记机器上抓一份 `getKGStatus` 的 `certs`（同型号更好），试能否复用；
2. 或者绕开 provision：不换证书，改为伪造 **用三星证书签名的 `regInfo`/policy**（需要签名私钥，
   只能靠真实登记）。

另外记一个运维坑：**改过的 base.apk 在重启后会被 PackageManager 重新提取覆盖**（`/data/app`
目录 hash 都变了，`pm uninstall-system-updates` 也失败），所以每次重启都要重新
`cp` 补丁包 + `chown system:system` + `chmod 644` + `chcon apk_data_file` + `cmd package compile -f`。

## 复现脚本

环境已脚本化（前置：root + `/data/local/tmp/apexcerts` + `/tmp/kgcerts/status.json` + `/tmp/self_final.apk`）：

```bash
./scripts/temp_root.py            # 取 root
./scripts/apply_kg_patch.sh       # 每次重启后都要：装回打过 pinning-bypass 的 APK
./scripts/kg_mock_setup.sh start  # CA 注入 zygote ns / 443 全量影子 / adb reverse / mitmdump
adb shell su -c 'cmd jobscheduler run -f com.samsung.android.kgclient 16'
tail -f /tmp/kgreq.log            # 抓到的请求
./scripts/kg_mock_setup.sh stop    # 收尾
```

`kg_mock_setup.sh` **只建环境**，不含 APK 补丁（补丁请用 `apply_kg_patch.sh`）。

## 证书编码格式：base64 DER（不是 PEM）

试出的关键区分：

| 下发的 `certs` 形式 | TZ `provisionCert` 返回 |
| --- | --- |
| PEM 文本（带 `-----BEGIN…`） | **264**（解析阶段就挂） |
| base64(DER) | **4097**（解析通过，校验阶段挂） |

所以客户端是把字符串 **base64 解码成 DER 字节**再丢给 HAL，PEM 直接给会被当非法。
4097 之后再换过密钥类型/签发关系都没有变化：

- EC P-256 自签 → 4097
- 一张自签 CA 签其余三张（EC）→ 4097
- RSA 2048 + 同样签发关系 → 4097

结论：**4097 是证书本身不被 TZ 接受**（大概率要求链到 TZ 内置的三星根，或需要三星特定的
subject/EKU 标记），不是编码问题。再往下要么拿到真实证书，要么逐字节比对真机证书。

## 补丁 APK 的部署方式（重要修正）

`/system` 是只读，`cp` 到 system 路径会静默失败（尤其 PM 把应用还原成系统版之后）。
正解是 **bind mount**：

```bash
umount /system/priv-app/KnoxGuard/KnoxGuard.apk 2>/dev/null
# 文件必须 root:root + 644 + system_file 上下文，否则 ART 报 Writable dex file 直接崩
mount --bind /data/local/tmp/self_final.apk /system/priv-app/KnoxGuard/KnoxGuard.apk
chmod 644 /system/priv-app/KnoxGuard/KnoxGuard.apk
cmd package compile -f -m speed com.samsung.android.kgclient
am force-stop com.samsung.android.kgclient
```

`scripts/apply_kg_patch.sh` 已按这个方式改好。另外注意：补丁包要与 PM 当前记录的版本一致
（PM 现在记的是系统版 `3.2.76`，就用 3.2.76 的补丁包；用 3.2.91 的会版本/组件对不上）。

## 证书轮盘赌：全部 4097（记录，避免重复）

`TAInfo(2) = CertProvisioned = false` —— 本机 TZ **确实没有**任何证书，所以 provisionCert 是必经，
不是"重装"。

`certs` 字段按 base64(DER) 下发后，逐一试过下面这些组合，TZ 全部返回 **4097**：

| 试法 | 结果 |
| --- | --- |
| EC P-256 自签 | 4097 |
| EC P-256，一张自签 CA 签其余三张 | 4097 |
| 同上但四张全 `CA:TRUE` + `keyCertSign` | 4097 |
| RSA 2048，同上签发关系 | 4097 |
| 三星风格 subject（`C=KR/O=Samsung Electronics/OU=B2B/CN=KG …`） | 4097 |
| RSA 4096 | 4097 |
| 叶子字段里附带签发者 DER（自建链） | 4097 |

对比：PEM 文本 → **264**（解析失败）；base64 DER → 一律 **4097**（解析通过、校验失败）。

结论：**TZ 对 KG 的四张证书有内建校验（几乎只能是链到 TZ 内的三星根／或特定属性），
自签绕不过**。要继续必须拿到真实证书（同型号已登记机抓 `getKGStatus` 的 `certs`，
或服务端针对本机下发）。当前时间成本下不再盲试。

## 让 eu-gslu 请求真的打到 eu-gslu（而不是 404）

反向模式下 8443 的上游被固定成 `gsl.samsunggsl.com`，而 `/af/...` 这些接口属于
`eu-gslu.samsunggsl.com`，直接透传会得到 404。addon 里加了一行改写：

```python
if path.startswith("/af/"):
    flow.request.host = "eu-gslu.samsunggsl.com"
    flow.request.port = 443
    flow.server_conn.address = ("eu-gslu.samsunggsl.com", 443)
```

有了它就能用 `KG_STATUS_PASSTHROUGH=1` 让 `getKGStatus` 走真服务端做对照实验。

实测结果：服务端对一个**未登记**设备直接回 **204 No Content**（无 certs），
说明真实证书只会在登记/enroll 流程里下发，靠"蹭"公共接口拿不到。
