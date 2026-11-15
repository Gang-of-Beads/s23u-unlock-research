# 阶段总结（2026-11-14）

设备：SM-S918B / `S918BXXSAFZH3` / One UI 8.5。
状态：锁定、`green`、KG `Active`、未登记进任何 KG 租户、root 为临时（重启失效）。

**一句话**：本地能做的已经做完 —— 协议、TZ、TA、分区注入点全部打通，解锁只差三星签名侧/租户后台的输入。

## 已经拿下的

| # | 能力 | 成果位置 |
| --- | --- | --- |
| 1 | 临时 root（约 60 s，可复现，重启失效） | `scripts/temp_root.py`、`docs/temp-root.md` |
| 2 | `adb shell su` 长期可用（Shell 授权 + `root_exec.sh`） | `scripts/grant_su.sh`、`scripts/root_exec.sh` |
| 3 | KG 客户端 pinning 全绕过（改 TrustManager + 换 MPS 锚 + apex CA 注入 zygote ns） | `docs/kg-mock.md` |
| 4 | KG 协议全抓包（lookup / getKGStatus / getPolicy / report），驱动到 `provisionCert` | `docs/kg-mock.md` |
| 5 | ABL 闸门反汇编：`FUN_000742f0` 状态表 `[1,0,1,1,0,1]` | `docs/findings.md` §23 |
| 6 | EM TA 直连（QSEECom，绕开 binder/RILD） | `scripts/emworld.cpp` |
| 7 | steady 分区读写 + 注入点定位（idx3 = 0x2400/0x2c00） | `docs/findings.md` §26 |
| 8 | ESI 块 / 段 magic / TLV 格式（`TOKE` `DEVI` `ISSU` `VALI` `GRDB` `MODB` `INTE`） | `docs/findings.md` §26 |
| 9 | 灌 token 通道 + runbook | `scripts/eminst.cpp`、`docs/tooling.md` |
| 10 | 取证基线（四分区 sha256、oem_lock、PDP 头） | `evidence/20261113-1456/` |

## 试过但无效（别再重复）

- 降级 One UI 7：rollback index 10 > One UI 7 的最高 9，ARB 拒；**改二进制位也不行**，
  计数器在 TZ/RPMB（PIT 无 ARB 分区），改镜像字段又会破坏 AVB（`findings.md` §41/§43）。
- 改 `param[0]`：只切启动模式（1=正常 3=Download），不解锁。
- 写 `devinfo+0x0d=1`：跨重启保留，但仍 `green`、仍 `-5`（闸门先看 KG）。
- `resetRPMB` / `setCheckingState` / `unlockScreen` / `kg30_*`：全部无效；
  会话打通后重测仍如此（`setCheckingState` 被 TZ 回 262，`unlockScreen` 返 0 但不改状态）。
- 自签 KG 证书 7 种组合：TZ 一律 `4097`；PEM 甚至解析阶段就 `264`。
- `reboot edl`、misc BCB `boot-into-edl`：都只回普通重启。
- 只有 `TOKE`/`NNTC`/ESI 块/`3f e4 e4` 前缀而无真 token：TA 一律 `0xf02d0010`（该码被多条分支共用）；
  ESI 块首 0x20 字节被清则退回到该码，说明那 0x20 字节是被校验的头，且 TA 内有
  `em_crypto_hmac`/AES-GCM 全套 helper + 设备绑定种子（`getTAInfo(4)`）→ 头大概率是 HMAC，自算不出来。三个对照实验（清头/清 item/单字节翻转）也证实块首是完整性字段：
动一个 bit 就 `0xf02d0010`，而改 item 里的 DID 只到 `0xf00b0010` → 伪造必须重算头，只有真 token 能让 TA 自己重写。
- **用 root 直接 dd 写 patched `init_boot`**：写进去了，但开机 AVB 拒绝 → Security Error 界面
  （KG 检查只在 Odin 会话里，dd 能过；kill 掉的是开机验签这第二道门）。见 `findings.md` §28。
- 恢复手法（已验证）：进 Download → `heimdall flash --INIT_BOOT /tmp/fwimg/init_boot.img`
  → 正常开机 → 重跑 `temp_root.py`。

## 名词解释（这三条路到底指什么）

**KG（Knox Guard）** —— 三星给渠道/租赁商的「设备管控」服务，按 IMEI 把机器登记进某个**租户（tenant）**。
登记后设备会从服务器拿到 policy 和证书，KG 状态随之变化；租户管理员可以在后台**放行（unlock/remove）**
这台机器。我们的 `-5` 就是 KG 状态不过闸门导致的，所以「登记进租户 → 后台放行」是**纯服务器侧**的正解。
（它和解 bootloader 不是一回事，但闸门只认 KG 状态，所以够用。）

**EM token（工程模式令牌）** —— 三星签名的二进制块，里面带「允许哪些工程模式」，装进 TEE（`steady` 分区）
后 `GetEMBit(3)` 变成 1，`devinfo.IsUnlocked` 才会真正生效。签名是三星 RSA 锚 + 设备绑定（DID/nonce/有效期），
**本地造不出来**，只能向三星的服务器要。

**ESS / DASEUL** —— 发这个 token 的那套服务器/通道。历史上是服务中心用的工程流程（工程 SIM + 账号），
请求经 modem 的 OEM AT 命令走蜂窝数据发出去。所以「有服务的 SIM」指的是**让这台机真能上网并连到 ESS**；
我们现在 SIM 是 `LOADED,ABSENT`，`emEssCommand` 直接阻塞。

区别一句话：**KG 登记是「让别人在后台点一下放行」，EM token 是「找三星要一张签名通行证」。**

## 两条路哪条更容易

**先做 KG 登记。** 理由：

- 全在服务器侧，Wi-Fi 就够（`Locked→Active` 已经证明过走 Wi-Fi + 账号能改变状态，不需要 SIM）；
- 协议我们已完整掌握（lookup/getKGStatus/getPolicy/report 全抓过），设备侧不用再改一行代码；
- 失败也不会更糟 —— 只要账号还登着，最坏是被打回 `Locked`，还能恢复。

门槛只有一个：**一个能进 Knox Guard 控制台的账号 / 愿意帮忙的租户**。

EM token 更难，因为叠了三层不确定：
1. 通道没通 —— `emEssCommand`/`emGetTimeRequest` 阻塞，binder 与 RILD 两条客户端路径都还没打通，
   真给张 SIM 也得先补这段；
2. 资格未知 —— 零售 IMEI 会不会被 ESS 受理、要不要白名单/账号，没人公开过；
3. token 还绑定 DID，我们的 DID 前缀是 `20`，而对得上锚点的是审计机那种 `30` 前缀，锚点可能都不一样。

所以顺序：**KG 登记 → （仍不行再）EM token → （都不行）EDL。**

## 外部资料（2026-11 检索）

- `CamsShaft/arbitrary-R-W-for-steady-and-param-partitions`：uid 1000 读写 steady/param（frigate→`knox_native` socket）
  + **完整 token 格式与生成脚本**（`scripts/emtools/engmode.py`）。需要泄露的 rootCA 私钥才能通关。
- 固件清单核对（§41）：One UI 7 最高二进制 9 < 本机 10，**降级不可行**。
- XDA 4808477：One UI 8 的 `no_oem_unlock` 限制被蓝牙级复现（改 users.xml + `service call oem_lock`），
  结论与我们一致 —— **框架侧改完 BL 仍不解锁**，作者判断 BL 看的是 QFPROM `LCS STATE: PROD(3)`。

## 三条路（都需要外部条件）

1. **KG 进状态 1/4** —— 让机主/商家把本机 IMEI 加进他们的 KG 租户（`registered:true` → enroll）。
   成功后 `provisionCert` 会有真证书，闸门直接放行。
2. **拿签名 EM token**（格式已公开，缺的是三星工程**叶子证书+私钥**。`findings.md` §40/§42） —— 有 token 后按 `docs/tooling.md` 的 runbook 灌入（工具必须改名 `emservice`）。
   需要 ESS 通道：自带服务的 SIM 或 ESS 凭据。ESS 走 CP，`emGetTimeRequest`/`emEssCommand` 现在会阻塞。
3. **EDL（9008）** —— 免拆短接线在 S23/S24/S25 上有成功案例；但检索显示
   **locked BL 下 EDL 刷 custom 基本无人成功**（刷完 "SYSTEM HAS BEEN DESTROYED"）。
   价值是救砖 + 读写 + 做实验，不是解锁。见 `findings.md` §45。

## 环境现状的坑（做 EM/ESS 前先处理）

- SIM 是 du（424/03），能收到 GSM（-81 dBm）但 `mVoiceRegState/mDataRegState=OUT_OF_SERVICE`、
  `regState=NOT_REG_SEARCHING`，漫游已开也没注册上 → 没有蜂窝数据。
- Wi-Fi 也没连上（保存的网络 `AstraTech` 当前不在扫描结果里），设备实际**完全离线**。
- ESS 走 CP，没蜂窝到不了 ESS；KG 只要账号还登着，离线一般不影响（`Active` 稳定）。

## 绕过路线总表（按性价比排序）

前提：`-5` = ABL 的 KG 内容闸门（表 `[1,0,1,1,0,1]`，只放行 1/4），后面还有 AVB。
**任何一条都必须先让状态过闸门，再谈刷写。**

| # | 路线 | 需要什么 | 现在到哪一步 | 成功率 | 代价 |
| --- | --- | --- | --- | --- | --- |
| 1 | **KG 租户登记 + 后台放行** | 一个能进 Knox Guard 控制台的账号 / 愿意帮忙的租户 | 协议全抓、HAL→TZ 会话可建、状态可读（恒 2） | **高**（只要有人肯加 IMEI） | 找人；纯服务器侧，Wi-Fi 就够 |
| 2 | **真 EM token** | 三星工程**叶子证书 + 私钥**（SPKI 被 pin、CN 必须 `EngineeringMode`、RSA-2048） | 格式已公开、解析已走到签名层（`0xf02b0010`）、灌入通道与 runbook 齐备 | 中低（公开渠道暂无证书） | 找服务/店家代签，或等泄露 |
| 3 | **EDL（9008）** | 开背盖短接测试点 / EDL 线 + firehose | loader 公开可得，CVE-2026-25262 备选 | 中（能绕 `-5` 直写分区） | 动硬件；仍要处理 AVB（vbmeta+init_boot 一起动） |
| 4 | **TZ 侧漏洞** | 研究投入 | 审计仓库给过候选面（如 HAL `getBytes` 未校验 `mLen` 的堆溢出） | 未知 | 高，纯研究 |
| 5 | One UI 7 降级 | —— | 二进制 9 < 本机 10，ARB 必拒，计数在 TZ/RPMB | 低（需先有写 TZ 的能力） | 16 GB 下载 + 白折腾 |

### L2 已判负（2026-11-14）

换二进制 A 里最早的 AFZE1 整套 BL，长按音量上仍**毫无反应** —— 老 ABL 也把入口摘了。
另外确认 `abl` 由 `vbmeta` 哈希校验，BL 任何一件都不能单换。详见 `findings.md` §48/§49。

### L5 需要客户端配合

`verifyRegistrationInfo` 盲喂只能到 264（只有字符串形状能进解析）。要推进必须在 MITM 里让客户端跑
enroll，从 HAL 日志取真实 regInfo 形状。见 `findings.md` §50。

### 客户端补丁：组件启用已打通（§52）

新版本客户端已能重建补丁并跑起来（注入 `KGApplication.enableAll` 打开全部组件），
enroll 界面能打开但停在 "Please wait…"、未发出 HTTP，卡在**前置状态**。见 `findings.md` §52。

### 明确无效（不必再试）

`param[0]`、`devinfo+0x0d=1`、PDP 位、`persist`/`sys.usb` 类 prop、直接 `dd` patched `init_boot`、
`resetRPMB`/`setCheckingState`/`unlockScreen`/`kg30_*`、七种自签 KG 证书、`reboot edl` 与 misc BCB、
自签 EM token 的所有前缀/长度组合。

### 只治表面的

- KG 客户端「绕过」教程（`device_provisioned=0` + AppOps 冻 EMM）：只是不想看锁屏，
  **不改 TZ 状态**，`-5` 照旧；
- `frigate`/`knox_native` socket 读写 steady：我们有 root + QSEECom，比它更直接；
- 框架侧复现 OEM 解锁开关（改 `users.xml` + `service call oem_lock`）：能点亮开关，
  BL 不认（XDA 同结论）。

### 结论

**先走 1。** 只有它不需要证书、不需要硬件、也不需要新漏洞；拿到放行后立即
`heimdall flash --INIT_BOOT <patched>` 验证是否真的过了闸门（过了就等于持久 root 到手）。
2 作为并行线继续找证书；3 是兜底（也能救砖）。

## 风险与注意

- KG `Locked` 会锁屏并要求 KG PIN（服务器下发），届时只能靠机主登录账号 / 租户管理员 / 三星客服。
- 设置锁屏 PIN 会让 Download 模式 D2（USB 完全不枚举）。要进 Download 就先
  `cmd lock_settings clear --old <pin>` + `set-disabled true`。
- 改过的 `base.apk` 重启会被 PM 重写，pinning 绕过要在重启后重跑 `scripts/apply_kg_patch.sh`。
- `steady` 现有内容是我们写的实验数据，原件在 `/data/local/tmp/steady.bak`。
