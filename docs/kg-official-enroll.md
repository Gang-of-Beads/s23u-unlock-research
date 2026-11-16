# 官方免费路线：自建 Knox Guard 租户 → 让设备到 Completed（ABL 闸门放行）

> 依据：ABL 闸门表 `[1,0,1,1,0,1]` 按 KG state 索引，**只有 1(Checking) 和 4(Completed) 返回"放行"**；
> 我们设备现在是 2(Active) ⇒ 被拒。
> 而"把设备标成完成/解锁"正是各家工具里的标准做法（Cheetah Tool 的 KG 面板直接列
> `Checking / Locked / Completed` 三项，Completed 就是解锁）。
> 关键点：这不是靠假数据，而是**用三星自己的服务签发真策略**，TA 会真接受。

## 为什么这条是"官方"的

Knox Guard 对所有人开放，且**试用许可免费**：

- 官方文档 `manage-licenses`：Trial 许可 **3 个月激活期、3 年设备使用期、30 个席位、免费**，
  在控制台 Licenses 页自助生成。
- 官方文档 `kba-1706`：过了 7 天窗口后，设备用户可以在设备浏览器打开
  `https://guard.samsungknox.com/` 点 **"Enroll this device"** 自行触发登记。
- 官方文档 `knox-guard-status-flow`：管理员把设备标记完成 → `Completing` → 2 天后 `Complete`，
  期间可撤销；设备侧对应 state 4。

因此流程完全是"正规入网 + 正规完成"，不需要任何私钥或泄漏证书。

## 步骤（草案）

0. 前置：设备现在被别的租户管着（`Active`）。先在 **我们自己的控制台**里 `Enroll this device`，
   让登记转移到我们的租户（转租户这一步若被拒，就先恢复出厂，见风险）。
1. 注册 Samsung 账号 → 申请 Knox 试用（Licenses 页生成 Trial 许可，30 席位）。
2. **把设备恢复原样**：`scripts/kg_mock_setup.sh stop`、撤掉 bind mount 的补丁 APK、
   删 `KG_shared_pref.xml` 里的 `KG_SERVICE_URL`/`KG_UMC_CDN_URL`（否则还在打我们的 mock）。
3. 设备联网，用 Chrome/WebView 打开 `guard.samsungknox.com`，登录后点 `Enroll this device`。
4. 控制台里接受设备（若配置为自动接受则跳过），设备状态 → `Activating` →（联网）→ `Active`。
5. 控制台里对该设备执行 **Unlock / 标记完成**，等设备拉到真策略（`getKGStatus`/`getPolicy`
   走真服务器），状态 → `Completed`。
6. 设备上查 `getprop ro.boot.kg`（应为 `0x4`）→ 关机进 Download → 试刷 patched `init_boot`。

## 风险与注意

- **登记转移**可能要求设备不在其他租户的 `Active`，最坏情况要恢复出厂（本来也要清数据）。
- 试用许可会消耗 1 个席位；30 个够折腾。
- 设备端 KG 客户端必须能用：我们改过 `LaunchActivity`/`BrowserEnrollmentActivity`，
  手动登记时可以先用原版 WebView 流程；若补丁 APK 与新流程冲突，先 `umount` 回原版。
- 进 Download 仍需注意 D2：登记/完成后不要先设 PIN；万一进不去，用文档里的 22 键 OTP 屏。
- 别把试用席位用在别的机器上，保留给本机复现。

## 与 mock 路线的关系

mock 那条（`docs/kg-mock.md`）证明了协议格式；这条**不需要**它。
两者可共存：先跑官方路线，若失败再回到 mock 深挖。
