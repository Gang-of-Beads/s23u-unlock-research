# 阶段总结（2026-11-14）

设备：SM-S918B / `S918BXXSAFZH3` / One UI 8.5。
状态：锁定、`green`、KG `Active`、未登记进任何 KG 租户、root 为临时（重启失效）。

**一句话**：本地能做的已经做完 —— 协议、TZ、TA、分区注入点全部打通，解锁只差三星签名侧的输入。

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
