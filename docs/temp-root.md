# 临时 root 流程（已验证两次，重启失效）

> 现状/卡点总览见 `docs/summary.md`；root 只是手段，解锁主线看那里。

锁定态下唯一可用的 root 方式：**Root My Galaxy 0.6.0 的 BOPE 载荷**（CVE-2026-43499，内核任意写
+ 伪造 fops，2–8 秒成功）。它是运行时注入，不碰任何分区。

## 前置

- 设备已开机且**运行 ≥ 60 秒**（App 里有 `uptime-gate`，最低 60s），不要在刚开机时跑。
- 内存尽量空：先 `am kill-all`，把不用的第三方 App `force-stop`（App 自己也会 quiesce 29 个进程）。
- 温度不要高（App 有 3 次稳定性采样，>45 ℃ 会等）。
- Shizuku 必须已启动：`moe.shizuku.privileged.api`，用
  `adb shell <nativeLibDir>/libshizuku.so` 拉起，App 侧 runner 走 Shizuku。
- 检查 `persist.sys.usb.config` 无关；USB 只要 adb 通即可。
- 管理器 `Superuser` 里 **`Shell`（`com.android.shell`）** 必须是 `ROOT`（用
  `scripts/grant_su.sh Shell` 一键搞，幂等）——这是让
  `adb shell su` 可用的关键（一次性设置，长期有效）。给 Termux（`com.termux`）也授权同样有效，
  两条路都备着。授权前 `su` 在 shell 侧**连文件都看不见**（KernelSU 的 overlay 只挂进已授权域的
  挂载命名空间），表现为 `/system/bin/su: No such file or directory`。

脚本：`scripts/temp_root.py`（自动做 uptime 检查、清进程、起 Shizuku、点按钮、轮询结果）。

**它先探测 `su -c true`：已经有 root 就直接退出、不碰载荷**——root 还活着时重跑会把现有 root
打掉（历史事故）。确实要重来才加 `--force`。
App 的 History 页会记录每次 `Succeeded` / `Failed`，**那是唯一可信的判定**。

## 步骤

1. 启动 Shizuku（`scripts/temp_root.py` 已封装；手动版如下）：
   ```bash
   lib=$(adb exec-out pm path moe.shizuku.privileged.api | tr -d '\r' \
        | sed 's/package://;s#/base.apk#/lib/arm64/libshizuku.so#')
   adb shell "$lib"          # 输出 info: shizuku_starter exit with 0
   ```
2. `adb shell monkey -p io.github.rootmygalaxy.s23ultra 1`
3. 点 `Tap to install KernelSU Next`（首装）或 `Tap to try again`（重试），再点 `Confirm`。
4. 等 10–40 秒，直到界面出现 `Root Active` / `4 of 4 · Complete`；History 会记一条 `Succeeded`。

## 验证

- App 界面出现 `Root Active` / `4 of 4 · Complete`，History 记 `Succeeded`。
- 管理器 `Home` 显示 `Working`（`LKM (GKI2)`）。
- 真正的可用性判据是 Termux 里 `su -c id` 返回 `uid=0(root)`；拿不到就按下一节处理。
- `cve43499-hold` 进程很短命，`ps` 里查不到不代表失败。

## 失败处理（实测）

- 第 3 步（`3 of 4 · Root`）失败时界面会给红卡
  `Reboot required / The payload failed after changing kernel state. This boot may be inconsistent`。
  **必须重启**再试，同一次开机会连着失败。
- 重启后要等 ≥ 60 秒（uptime gate），顺手 `am kill-all`。等够了基本一次过（`Root achieved in 3–8 seconds`）。
- 反复失败时先去 History 确认是 `Failed` 还是其实已经 `Succeeded`，别重复点。

## 拿到 root shell（已可用，走 adb）

管理器 `Superuser` 给 `Shell` 授权后，**`adb shell su` 直接可用**：

```
$ adb shell su -c id
uid=0(root) gid=0(root) groups=0(root) context=u:r:ksu:s0
```

- `su`、`/system/bin/su`、`/data/adb/ksu/bin`（`ksud`、`resetprop`、`busybox`）都可访问。
- Termux 授权后同理，Termux 里 `su` 也能用；两条路都在。
- 统一用 `scripts/root_exec.sh '<命令>'`（或 `-f 脚本`）执行并回读输出：优先 adb 的 `su`，
  Shell 未授权时自动回退 Termux 输入法。实测一条命令约 1.5 秒。
- 授权状态可查：管理器 `Superuser` 里对应项显示 `ROOT`；`adb shell su -c true` 返回 0 即可用。
- 重新授权（重启后 `su` 消失时先确认是「掉 root」还是「授权被关」）：`scripts/grant_su.sh Shell`。

## 重要限制（别浪费时间）

1. 权限来自管理器授权，**不是**自动的：`Superuser` 里没给 `Shell` / `Termux` 授权时，`su` 在那边
   根本不可见。未授权时不要把 `/system/bin/su` 的 `No such file or directory` 当成没装好。
2. `/data/local/tmp/temp_su.sock` 对 `shell`、`untrusted_app_27`、`untrusted_app` 都是
   `Permission denied`，它只服务 App 自己的 bootstrap；**别再用它**，直接走 `su`。
3. root 生命周期极短：App 跑完即 `Reboot required`、holder 退出；Termux 里已经开着的 `su` 会话
   会跟着失效，重启后一律要重新取。**要用就在成功后的几十秒内用掉。**
4. `su` 在 Termux 里能用，是因为管理器/`ksud` 已经把 `/system/bin/su`、`/data/adb` 就位；
   但重启后这些挂载不在了（要重跑引擎）。真正持久化仍得刷补丁 `init_boot`，而它被 `-5` 拦住
   （见 `findings.md`）。
5. 模块 stage 脚本（`post-fs-data.sh` 等）不会自己执行，别指望靠模块做开机逻辑；
   有 root shell 时直接手跑 `ksud post-fs-data` 更省事。

## 拿到 root 后能做什么（实测）

> root 只剩几十秒，**立刻**做需要 root 的事；别指望重启后还在。

- 管理器 `Home` 会显示 `Working` / `LKM (GKI2)`，`Superuser` 与 `Module` 计数可用。
- 管理器**能**以 root 执行 `ksud`：走 `Module → Install → 选 zip` 会返回 `Flash success`，
  模块确实装进 `/data/adb/modules`。
- 但**模块脚本不会自己跑**：v2 模块同时带了 `post-fs-data.sh` / `late-load.sh` / `service.sh` /
  `boot-completed.sh`，安装（`Flash success`）后四者都没执行，`mroot.log` 始终不出现——
  因为没有任何东西调 `ksud post-fs-data`（缺 init 钩子）。这是当前的缺口。
- root 下可用 `/data/adb/ksu/bin/ksud`（含 `resetprop`、`boot-patch`、`sepolicy`、`install`）
  与 `/data/adb/ksu/bin/resetprop`。注意：**从 adb shell 直接跑 ksud 仍失败**
  （`/data/adb/ksu/bin is not a regular directory`），必须经 Termux 的 root。

## 探针模块

`scripts/build_probe_module.sh [--job '<命令>']` 生成 `rcprobe` 模块并推到
`/sdcard/Download/rcprobe.zip`；默认 job 是记录 uid/SELinux 域并给 `param`/`persist`/`misc`
做 sha256。装法：管理器 `Module → Install → My Files → Download → rcprobe.zip → Done → OK`。

## 手工起载荷（不依赖 App，目前未跑通）

App 实际执行的是：

```
/data/local/tmp/stability-launcher --payload /data/local/tmp/ksu-payload \
    --helper /data/local/tmp/ksu-helper --mm-factory /data/local/tmp/mm-exec-factory
```

载荷按构建号选：`assets/cve-2026-43499-app-afzh3.so`（sha256 `8dd9036c…d3fc`）推到
`/data/local/tmp/ksu-payload`。

手工跑能过 gate、能定位内核，但卡在：

```
[preflight] mm_struct geometry/load rejected size=1024 per=32 pages=8 active=1857 total=1920 slabs=60
```

三次尝试全部同一处被拒，`--conservative` 无效；杀光第三方进程后 `active` 仍是 1857（说明不是简单的
进程数问题）。App 侧能过，推测差异在 App 设置的载荷环境变量（`RMG_RECLAIM_MIN_FULL`、
`CVE43499_ROOT_HELPER`、`CVE43499_MM_FACTORY`、`EXPLOIT_ATTEMPTS`、`P0_PROBE_PAGE_STRUCT`、
`BISECT_VARIANT` 等），尚未逐项复现。

## 卸载 / 复原

- `adb shell` 删 `/data/local/tmp/{ksu-payload,ksu-helper,ksud-selected,mm-exec-factory,stability-launcher}`，
  重启后即无 root；`/data/adb` 内容留在数据分区（下次重装会被 `ksud` 覆盖）。
