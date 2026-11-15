# 解锁 BL 的可行路线（网络调研，2026-11）

> 前提：One UI 8 起三星把 BL 解锁代码从 ABL 里整体剥掉，社区（`bootloader-unlock-wall-of-shame`）
> 直接把三星标为 **Impossible**。官方 toggle 不再存在，本机又已被 KG 卡在 `Active`。
> 因此下面只列“还能动”的路，并给判断。

## A. EM token（当前最优，值得花钱）

- **是什么**：三星工程模式 token，含 mode 位图；我们反出来的 ABL 里 `GetEMBit(3)` 直接驱动 `SetUnlocked`。
- **谁卖**：
  - Global Unlocker Pro，`Write Token EM-TOKEN`，**4.00 credits/次**，最小起充 5 credits（global-unlocker-pro.com）。
  - SAMTOKEN（sam-token.com），专营 E-Token/EM-Token，WhatsApp 报价。
- **为什么可行**：token 由三星服务端签发，是"合法签名数据"，正是 TZ/ABL 唯一认的东西；
  且灌 token 的通道我们自己已经有了（`scripts/eminst.cpp`，QSEECom 直连 TA）。
- **风险**：卖家默认用途是刷 combination / IMEI 修复，不一定给带 mode 3 的 token —— 必须提前确认。
- **步骤**：问清支持 S918B+XSG、含 mode 3 → 买 → `eminst` 灌 → `emInit` 应返回 0 → 查 `getModesBit` bit3
  → 重启看 `verifiedbootstate`。

## B. Combination 固件（和 A 绑在一起）

- 刷 combination（工厂二进制作业系统）本身就要 EM token，所以 A 拿到就顺带可做。
- 意义：combo 自带 engineering 侧设置，是唯一"能看见 OEM 解锁相关项"的环境；
  即使 A 的 token 没带 mode 3，先刷 combo 进工程环境再想办法也是备选。
- 代价：全盘擦除。

## C. EDL / firehose（能绕过 Odin 的 ARB 与哈希）

- **现状**：我们的 bit（A）的 firehose 已被公开：
  `Alephgsm/SAMSUNG-EDL-Loaders` 的 `S918B_Loader_alephgsm.com.elf`、`SM-S918B_prog_firehose_ddr.elf`；
  XDA 4789266 里还有人贴了 `S918B-BIT-A-prog_firehose_ddr.zip` 与 firehose 抬头（`anti_rollback_version: 7`、
  支持 `patch`/`program`/`erase`/`fixgpt`）。
- **能做**：raw 写任意分区（param / devinfo / persistent / abl / vbmeta），**绕过 Odin 的 ARB 和哈希校验**。
- **不能做**：开机时 ABL/vbmeta 的验签照样在，写进去的东西不合法就不启动。
- **进入方式**：`reboot edl` 在本机不通，需要 **EDL 线 / 测试点短接**（我们之前判断"值得买一条"）。
- **定位**：救砖 + 配合 A（万一 Token 写入被 Odin 侧拦），也是唯一的"物理级"兜底。

## D. 老办法（已证实对本机无效）

- 通过 root 改 `persistent`/`param` 里的 `oem_lock`、`devinfo+0x0d`：都试过，ABL 不认（§21/§44）。
- `KnoxGuardManager` 的 `unlockScreen()`/`resetRPMB()`：返回 0，无实际变化（§30）。
- 改属性 `knox.kg.state` / `ro.boot.other.locked`：只是显示层。
- 改二进制位：counter 在 TZ/RPMB，PIT 里没有 ARB 分区（§43）。

## E. 第三方盒子工具（未验证，仅记录）

- UnlockTool / Chimera / TFT 一类盒子确有"Samsung BL unlock"条目，但基本针对旧机型或已解锁场景；
  One UI 8 + KG Locked 组合目前没有公开成功案例。若已有这些工具，值得试一次，不值得为此新买。

## 结论

**买 EM token（A）是唯一有明确机制支撑的软件路子**，C 是物理兜底，B 是 A 的后续，D/E 基本无望。
花钱前先确认 mode 3；失败也只损失几美元，不动数据。
