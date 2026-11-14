# SM-S918B（S23 Ultra，中东版）解锁 + Root 实录

目标：解锁 bootloader 并取得持久 root。**结论：本地能做的已经做完，解锁卡在三星签名侧。**

## 结论先说

1. 设备**没有真正解锁**（`warranty_bit=1`、`ulcnt=3`，但 `verifiedbootstate=green`、
   `device_state=locked`）。改过的引导镜像一律被 ABL 以 **`-5`** 拒刷，原厂内容可以刷。
2. `-5` 的根因是 **KG（Knox Guard）内容校验**，与「解锁状态」无关。反汇编出来的闸门
   `FUN_000742f0` 按 KG 状态查表 `[1,0,1,1,0,1]`：只有 **1(Checking)/4** 放行，
   **Active(2) 和 Locked(3) 都拒**（所以「把 KG 弄成 Active」不会有任何帮助）。
3. 本机 KG 是 `Active`、真实 lookup 返回 `registered:false`（**未登记进任何租户**）；
   `Locked→Active` 是靠登录三星账号恢复的（服务器侧状态）。
4. 「降级 One UI 7 再解锁」对本机不可行：rollback index 已是 `10`，One UI 7 只到 binary 8/9。
5. 现在只剩三条外部依赖的路（`docs/summary.md`）：KG 进 1/4、三星签名的 **EM token**、动硬件走 EDL。

## 设备与软件基线

| 项 | 值 |
| --- | --- |
| 机型 | SM-S918B / dm3q（中东版，OXM 多 CSC，当前 CSC `XSG`） |
| 序列号 | R5CWAXXXXX |
| 平台 | SM8550 / Kalama，UFS，A-only（无 slot 后缀） |
| 当前构建 | `S918BXXSAFZH3`（One UI 8.5 / Android 16，二进制位 `A`，rollback index 10） |
| 原始构建 | `S918BXXUAGZIF`（One UI 9 / Android 17，二进制位 `A`） |
| warranty_bit | 1（Knox 熔断，Samsung Pay / Pass / Secure Folder 不再可用） |

## 当前状态（2026-11-14）

- 系统：One UI 8.5 正常开机，数据全清；KG `Active`、`green`、无 PIN、keyguard 已禁用。
- Root：KernelSU-Next **临时 root** 可稳定复现（BOPE 载荷，约 60 s），**重启即失效**；
  `Su` 给 `Shell` 授权后 `adb shell su` 可用。持久化（刷 patched `init_boot`）卡在 `-5`。
- `devinfo+0x0d`（IsUnlocked）被写成 `1` 并跨重启保留，但仍是 `green`、仍 `-5`。
- 有 root 后试过直接 dd 写 patched `init_boot`：**写得进去，但开机 AVB 拒绝**（Security Error 界面）。
  「临时变永久」要过两道门（Odin 的 KG 内容校验 + 开机 AVB 验签），dd 只买到第一道（`docs/findings.md` §28）。
- 已刷回原厂 `init_boot` 并恢复临时 root。
- 开机 USB 默认模式已改为 **文件传输 + adb**（`settings put secure default_usb_configuration mtp`，
  两次重启验证稳定；用 `persist.sys.usb.config` 会被覆盖，见 `docs/findings.md` §29）。
- `steady` 分区被写入过实验数据，原样备份在 `/data/local/tmp/steady.bak`。

## 已打通 / 卡点

| 能力 | 状态 |
| --- | --- |
| 临时 root（重启失效） | ✅ `scripts/temp_root.py` |
| KG 全链路 MITM（pinning 绕过、真实协议抓齐） | ✅ `docs/kg-mock.md` |
| 假 enroll 到 `provisionCert` | ✅（TZ 对自签证书返 `4097`，要真证书） |
| EM TA 直连（QSEECom，不经 binder/RILD） | ✅ `scripts/emworld.cpp`（uid 1000 + 进程名 `emservice`） |
| steady 注入 / ESI 块与段格式（`TOKE`/`DEVI`/`ISSU`/`VALI`/`MODB`/`INTE`） | ✅ 已逆清 |
| 灌 token 通道 | ✅ `scripts/eminst.cpp` + runbook（`docs/tooling.md`） |
| **拿到真 token** | ❌ 需要 ESS 或带服务的 SIM（本机 SIM `LOADED,ABSENT`） |
| **让 KG 进 1/4** | ❌ 需要租户登记或能过 TZ 的 certs |
| EDL（绕开 `-5` 直接读写分区） | ❌ 需动硬件（测试点/EDL 线），`reboot edl` 与 misc BCB 都无效 |

## 下一步（详见 `docs/summary.md`「绕过路线总表」）

排序：① **KG 租户登记/后台放行**（唯一不需证书、不需硬件、不需新漏洞的路，只差一个账号）；
② 真 EM token（格式已公开，缺三星工程叶子证书+私钥）；③ EDL 兜底（需动硬件，且仍要处理 AVB）；
④ TZ 漏洞研究；⑤ One UI 7 降级（ARB 必拒，属回头路）。

## 文档

- `docs/summary.md` — **阶段总结：能力、工具、证据、卡点（先看这个）**
- `docs/findings.md` — 全部实测结论与错误码（含每条的证据）
- `docs/d2-kg-lock.md` — D2 错误与 KG 锁定的坑与恢复通道（动 KG 前必读）
- `docs/kg-mock.md` — 假 KG 应答方案：pinning 绕过、真实协议、证书轮盘赌
- `docs/temp-root.md` — 临时 root 的固定流程与硬限制（别重复摸索）
- `docs/tooling.md` — 工具链：heimdall、Ghidra/REA、EM TA 直连、token runbook、UI 自动化约定
- `docs/hardware.md` — 硬件/固件/安全基线（含序列号）
- `docs/procedure.md` — 刷机可复现流程
- `docs/kgndk.so`、`docs/kgd.dis`、`docs/ot.dis` — KG HAL stub 与反汇编（AIDL 方法表取证）
- `unlock-checklist.md` — 早期通用清单（已被推翻，留作按键参考）
- `evidence/` — 只读取证快照（四分区 sha256、KG/oem_lock 状态、PDP 头部），用于 diff

## 大文件（不入 git）

工作目录里的 `SM-S918B_..._XSG.zip`（约 16 GB）、解出的 `*.tar.md5` 与镜像均在本地，`.gitignore` 已忽略。
