# D2 隐藏 OTP/QR 授权屏 — 实机抓取

- 设备：SM-S918B / AFZH3（`BP4A.251205.006.S918BXXSAFZH3`），KG `Active`，Wi-Fi 开
- 触发：`locksettings set-pin 1234` → `adb reboot download` → 停在无 USB 的 D2 屏
  → 按住 Power，Vol+ ×8、Vol- ×5、Vol+ ×9
- 结果：出现 QR + 选项菜单（屏幕照片未入库，见下方 QR 原文）

## QR 原文（base64）

```
RDIwMTEwMDA0UzkxOEJYWFNBRlpIM2BgYGBgYGAy6WV/iQQvRupOBPRmFsO64Abcl/cnc+JGIfwFmHcngMnezW7pYxFdkFt9XFNlLxaSq8GoehunT6H3YL3Af//3JtSHVX6RhFwOQwm7LS99723DywuTqj6Uqz9HsPmoKXOq6bDRL3s6l4mJUfH/VkDYRwBzxOngg2fwKm3RCWIrexumvyzC6xdHdtO2ax0WbbczqsEgQv+oRcnY2L8o5wrY/9oZMKNgglkLTBvk34vy74u+DPn4J+KmnmxcQUMaLkvBL4700+K3i2yT81ySp9o+pSIpDfOxR/z8fg0gP3dhdwiUs6N0UzWXO7fVTYkPb8PRk2aSME1VCKlwgkL27hkWva7UP4e3IHgA7Eyud4opetz0BHvn95XSa+Yn5skQViDzbR7AriFedKKna4K5034YOLYbe6sd1H3EZhFhG8hkTK8m+5AZt5WF3J26qGAkv3DhRSwS1LCvszS1BMkmDxhHc/YKrc5W4dS96wQRXO4RPdROgVzNzNLn7Konf+igyE+AOMN2Inv+9ZPNyYKquBmrkAIHrhIxvgQy6k2xN7D4m6EbEJNMjfZYBVSgIUoo2Jm1ndx1QFB+8Q4G6E4VxvLsMgUAQ3xmHlCalx36yLP6YtjK+MWXYth39tpNzFPxh8QFNAMyuaQ+GzZxm7LIvYLBmDdlUfi3gXWXA6MP4x8O5A==
```

## 解码结果

QR 文本是 base64，解出 **541 字节**（`envelope.bin` 原样保存）：

- `0..28`（29 字节）明文头：`D20110004S918BXXSAFZH3` + 0x60（`` ` ``）填充
  - `D2` = 屏标识，`10004` = PID，`S918BXXSAFZH3` = 软件版本，与文档的身份构建器字段（PID / 版本）对得上；
    尾部反引号是定点宽度的填充，印证"29 字节不透明前缀"。
- `29..540`（512 字节）密文体：RSA-4096 OAEP(SHA1)。固件里只有公钥，**8 位 OTP 必须私钥侧算**。

结论：这张 QR 就是"代签"要递交的全部内容；会话 3 次输错作废并换新 QR。
