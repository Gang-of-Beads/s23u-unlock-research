# scripts

> 全局现状与卡点见 `docs/summary.md`。

两个脚本都假设固件已解包到 `/tmp/fwimg`、映射表已生成到 `/tmp/pitmap.json`。

- `prep_fw.py` — 从工作目录的 `BL_/AP_/CP_/CSC_*.tar.md5` 里抽镜像、lz4 解压，
  按 PIT 的 `Flash Filename` 建分区映射，输出 `/tmp/flashplan.json`。
  未映射项应只有 `meta-data/fota.zip`（正常，非分区）。
- `sess1.sh` — 生成的 BL 段刷写命令（31 个引导分区）。
- `sess2.sh` — 生成的 AP/CP/CSC 段刷写命令（17 个分区）。

生成 `sess*.sh` 用的逻辑：从 `flashplan.json` 按 BL 分区名集合切两段，
拼成 `heimdall flash --<PART> <file> ...`。可参考 `docs/procedure.md` §4–§5 重生成。

注意：`DM3Q_EUR_OPENX.pit` 被 `.gitignore` 忽略，因为它是固件内容；需要时从 CSC tar 再取。

## KG 相关

- `kg_mock.py` — mitmproxy addon：透传真实 MPS 但把 CA 换成自己的、mock lookup/getKGStatus、
  其它回 200；请求都记到 `/tmp/kgreq.log`（见 `docs/kg-mock.md`）。
- `kg_mock_setup.sh [start|stop]` — 一次性建/拆环境（CA 注入 zygote ns、443 全量影子、
  adb reverse、三实例 mitmdump）。**只做环境，不含 APK 补丁。**
- `apply_kg_patch.sh` — 把打过 pinning-bypass 的 APK 装回去；**每次重启后必须重跑**。
- `kg_boot_capture.sh` — 抓开机时的 KG 报文。

## EM（工程模式）相关

- `emworld.cpp` — 直连 `EngineeringModeWorld`（QSEECom → engmode TA）：init/模式位/令牌状态。
  **运行名必须是 `emservice`**，且内部会降权到 uid 1000。
- `emtime.cpp` — 只跑 `emGetTimeRequest`（ESS 时间请求，缺蜂窝时会阻塞）。
- `eminst.cpp` — 灌 token（`emTokenInstall`），同样需改名 `emservice`。
- `emcli.cpp` — 早期 binder 尝试（Java/`HwBinder` 路线见 `docs/tooling.md`），保留备查。

## 与 root 相关的脚本

- `build_probe_module.sh` — 生成/推送 `rcprobe` 探针模块（默认给 `param`/`persist`/`misc` 做 sha256
  并记 uid），装进 KernelSU 管理器备用。
- `root_exec.sh '<cmd>'` / `-f 脚本` — 以 root 执行命令并回读输出（走 `adb shell su`，
  Shell 未授权会直接报错并提示）。
- `grant_su.sh [Shell|Termux]` — 在管理器里把某个主体的 Superuser 打开（幂等，读完即验证
  `su` 是否可用）；纯 uiautomator XML 定位，见 `docs/tooling.md`「UI 自动化约定」。
- `build_helper.sh` — 编译并推送 `helpers/Unrestrict.java`（清 `no_oem_unlock` 用户限制，
  配合 OEM 解锁开关使用，见 `docs/findings.md` 第 14 条）。
- `temp_root.py` — 按 `docs/temp-root.md` 自动取临时 root：先探测 `su -c true`（已有 root 直接退出，
  `--force` 才重跑）、uptime 门禁、清进程、起 Shizuku、XML 点按钮、失败自动重启重试；
  成功后立刻做需要 root 的事。日志 `--log`（默认 /tmp/temp_root.log）。
