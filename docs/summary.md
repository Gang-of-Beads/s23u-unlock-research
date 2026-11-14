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

- 降级 One UI 7：rollback index 10 > One UI 7 的 8/9，ARB 拒。
- 改 `param[0]`：只切启动模式（1=正常 3=Download），不解锁。
- 写 `devinfo+0x0d=1`：跨重启保留，但仍 `green`、仍 `-5`（闸门先看 KG）。
- `resetRPMB` / `setCheckingState` / `unlockScreen` / `kg30_*`：全部无效。
- 自签 KG 证书 7 种组合：TZ 一律 `4097`；PEM 甚至解析阶段就 `264`。
- `reboot edl`、misc BCB `boot-into-edl`：都只回普通重启。
- 只有 `TOKE`/`NNTC`/ESI 块而无 token 灌入：TA 一律 `0xf02d0010`。

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

## 三条路（都需要外部条件）

1. **KG 进状态 1/4** —— 让机主/商家把本机 IMEI 加进他们的 KG 租户（`registered:true` → enroll）。
   成功后 `provisionCert` 会有真证书，闸门直接放行。
2. **拿签名 EM token** —— 有 token 后按 `docs/tooling.md` 的 runbook 灌入（工具必须改名 `emservice`）。
   需要 ESS 通道：自带服务的 SIM 或 ESS 凭据。ESS 走 CP，`emGetTimeRequest`/`emEssCommand` 现在会阻塞。
3. **EDL（9008）** —— 绕开 `-5` 直接读写分区，可刷 patched `init_boot`、可随时救砖；
   需开背盖短接测试点或用 EDL 线。本机型号的 firehose loader 公开可得，
   另有 CVE-2026-25262（Sahara 任意写，可绕签名）作备选。限制：开机 AVB 仍在。

## 风险与注意

- KG `Locked` 会锁屏并要求 KG PIN（服务器下发），届时只能靠机主登录账号 / 租户管理员 / 三星客服。
- 设置锁屏 PIN 会让 Download 模式 D2（USB 完全不枚举）。要进 Download 就先
  `cmd lock_settings clear --old <pin>` + `set-disabled true`。
- 改过的 `base.apk` 重启会被 PM 重写，pinning 绕过要在重启后重跑 `scripts/apply_kg_patch.sh`。
- `steady` 现有内容是我们写的实验数据，原件在 `/data/local/tmp/steady.bak`。
