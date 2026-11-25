# 纯净 Debian 11 rootfs（海思机顶盒 U 盘强刷包）

## 成果

`/home/guigui/usbflash-debian11.zip`（380MB）—— 基于纯净 Debian 11 bullseye arm64，
不含海纳思预装的 NAS 服务。刷入后是一个干净的 Debian 基础系统 + SSH。

## 构建过程

1. 宿主 x86_64 上安装 `debootstrap` + `qemu-user-binfmt`（qemu-aarch64 用户态模拟）
2. `debootstrap --arch=arm64 --foreign bullseye` → chroot 里 `--second-stage`
3. 换用清华镜像源（Debian 11 已 EOL，官方 security 源 404）
4. 安装基础包：openssh-server / sudo / vim / procps / iproute2 / curl / systemd-sysv 等
5. 配置：root 密码 `histb`、时区 Asia/Shanghai、locale、fstab、ttyAMA0 串口 getty
6. **用原版 `rootfs-64.img` 作底**（保留 UUID `64139786-...`，fastboot 靠它识别）：
   挂载 → 删空 → 拷入新系统 → 卸载 → e2fsck 修复
7. 打包成 `backup-64.gz`（316MB），写入 backup 分区镜像（512MB ext4），
   转回 Android sparse 格式放进 U 盘包

## 验证

- rootfs img：e2fsck 无错误，UUID 与原版一致
- backup-64.gz：gzip -t 通过，解压后是 Debian 11 rootfs
- sparse 格式：转回 raw 后能正常 dump 出 gz，CRC/结构正确
- zip 完整性：unzip -t 通过

## 刷机方法

与原 U 盘强刷完全相同：
1. FAT32/USB2.0 U 盘，拷全部内容，保持 `mv200/` 结构
2. 接网线，短接 RN14 上电 → 5 秒放开
3. 等 5-8 分钟，恢复流程会把 backup 分区的 backup-64.gz 解压到 p9（rootfs）
4. 出现完成画面后再静置 5-8 分钟

## 登录后

- IP 由路由器 DHCP 分配（MAC `00:11:22:33:44:55`）
- SSH：`root` / 密码 `histb`（**建议首次登录后立即修改**）
- 串口：ttyAMA0 115200，root 自动登录

## 注意事项

- 这是纯净系统，**没有**海纳思的 Web 管理页和 NAS 服务，需要什么自己 apt 安装
- 内核仍是原版 4.4 BSP（eMMC/网络 built-in），Debian 11 用户态与 4.4 内核兼容良好
- 如果要加 WiFi 驱动，需用海思 SDK 编译配套模块（见主仓库 docs/wireless.md）
- `rootfs-64.img` 单独文件：`/home/guigui/debian11-rootfs.img`（1.1GB）
