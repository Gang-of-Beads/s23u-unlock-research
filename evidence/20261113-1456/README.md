# 只读取证快照

采集时间 2026-11-13 14:56 前后。设备状态：KG `Active`、锁屏关闭、无 PIN、root（临时，事后即失效）。
**全部只读**（`sha256sum` / `dd` 到 /data/local/tmp 后 `strings`，未写任何分区）。

文件：

| 文件 | 内容 |
| --- | --- |
| `partitions.sha256` | `param` / `persist` / `misc` / `persistent` 的 sha256 基线 |
| `props.txt` | KG/锁相关 prop（含 `ro.boot.kg=0x2`、`ro.boot.kg.bit=01`） |
| `oem_lock.txt` | `service call oem_lock 1/2/3/4/7` 原始应答 |
| `restriction*.txt` | `no_oem_unlock` 用户限制是否存在（存在） |
| `persistent_header_and_param_strings.txt` | `persistent` 头部 hex（PDP magic `0x19901873` 在 `0x20`）+ `param` 可读串 |
| `device.txt` | 指纹 / 序列号 / CSC / hardware |

关键观察：

- `ro.boot.kg = 0x2`、`ro.boot.kg.bit = 01`（锁定前是 `0x0`/`00`），说明 KG 已把锁状态写进引导参数；
  这同时印证「`-5` 是 KG 判定的内容校验」而非解锁状态。
- `persistent` 里 PDP 结构仍在（magic `0x20` 处），但解锁位区是**全 0**——恢复出厂后 AOSP 位被清，
  剩 `Service call oem_lock 3` 也回 0。
- `no_oem_unlock` 用户限制仍在（`/data/system/users/0.xml` 命中 1 次），说明入口虽可见但开关默认仍禁用。
- `ro.boot.other.locked=1`、`verifiedbootstate=green`、`warranty_bit=1`、`ulcnt=3` 与事故前一致。

用途：后续任何「拨开关 / KG 变化」都能与这份基线做 diff，判断有没有真写分区。
