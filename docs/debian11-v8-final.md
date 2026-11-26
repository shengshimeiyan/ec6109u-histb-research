# Debian 11 纯净系统 v8（最终可用版）

## 成果

v8 是在 EC6109-U/M（Hi3798MV200 / 1G / eMMC 4G）上**实测可用**的纯净 Debian 11 系统。
刷入后：`eth0` 100Mbps Full、DHCP 拿到 IP、SSH 公钥登录可用、0 个失败服务。

```
内核: 4.4.35_ecoo_82082668 (原版 BSP，稳定)
系统: Debian 11 bullseye (11.11) arm64
内存: 646Mi 中仅占 44Mi（海纳思原版占 247Mi）
磁盘: 3.1G 根分区仅用 498M
```

## 从失败到成功的完整排错链

构建纯净 Debian rootfs 本身很顺利（debootstrap + qemu-user-binfmt），
难的是让它在海思盒子上启动。以下是逐个排除的问题：

| # | 现象 | 根因 | 修复 |
|---|---|---|---|
| 1 | 停在"正在刷入"画面，网口不亮 | `/etc/fstab` 多了 `/dev/root` 挂载行，systemd 卡在挂载根分区 | fstab 只留 `tmpfs /tmp`（与原版一致） |
| 2 | 同上 | `default.target` 指向 `graphical.target`，无显示管理器时卡死 | 改为 `multi-user.target` |
| 3 | 同上 | Debian 11 systemd 247 默认 cgroup v2（unified），4.4 内核支持不完整 | bootargs 加 `systemd.unified_cgroup_hierarchy=0` |
| 4 | **黑屏，连完成画面都不出现** | 我修改的 bootargs.bin 从 65536 字节变成 65571（多了35字节），而恢复脚本用 `dd count=1024`（精确 65536）写入 p2，超界导致 bootargs 分区损坏 | 插入参数后从尾部填充区扣掉等量字节，**保持文件严格 65536 字节** |
| 5 | 同上 | sparse 镜像用了单个超大 chunk，U-Boot `mmc write.ext4sp` 处理异常 | 改为分块 sparse（最多 256 块/chunk） |
| 6 | 完成画面出现，但网口不亮 | 纯净 Debian 无网络管理服务，网卡从未被 up（`qdisc noop state DOWN`，networkd `SETUP=pending`） | 新增 `netup.service`：强制 `ip link set up` → 等 carrier → dhclient |
| 7 | 网口起来了但 SSH 连不上 | Debian 默认 `PermitRootLogin prohibit-password`（禁 root 密码登录） | 加 `10-root-login.conf` 允许密码登录 + 预装公钥 |

### 关键诊断手段：U 盘/TF 卡抓日志

盒子没有 TTL 串口、屏幕只有刷机图片不显示内核日志。我写了一个开机脚本
把 `dmesg`、`ip addr`、`systemctl --failed` 等写到 U 盘/TF 卡。
它直接揭示了：`eth0 state DOWN` + `networkctl SETUP=pending` → 接口从未 up。

### 关键参数：hieth 网卡

原版日志 `[55s] hieth ... eth0: Link is Up`，而我们的 `netup.service`
让 PHY 在 **8.9 秒**就 Link Up——网口只有 admin-up 后 PHY 才通电协商。

## 构建方法（可复现）

1. 宿主 x86_64：`apt install debootstrap qemu-user-binfmt`
2. `debootstrap --arch=arm64 --foreign bullseye` → chroot `--second-stage`
3. 换清华源（Debian 11 已 EOL，官方 security 源 404）
4. 装基础包：openssh-server / sudo / vim / iproute2 / dhclient / systemd-sysv 等
5. 配置：root 密码、时区、locale、fstab、ttyAMA0、networkd + netup.service
6. **用原版 rootfs-64.img 作底**（保留 UUID `64139786-...`，fastboot 靠它识别）：
   挂载 → 删空 → 拷入新系统 → 卸载 → e2fsck
7. 打包成 backup-64.gz → 写入 512MB ext4 backup 分区 → 转 chunked sparse
8. 同时修改 recovery 分区里的 `bootargs9-64.bin`（保持严格 65536 字节！）加 cgroup 参数

## 刷机方法

与原版 U 盘强刷相同：FAT32 U 盘 → 短接 RN14 上电 5 秒放开 → 等 5-8 分钟。

## 登录信息

- IP：DHCP 分配（MAC `00:11:22:33:44:55`），默认 `192.168.1.12`
- SSH：预装公钥 `pi-agent-nas-access`；也可用 root / 密码 `histb`（**首次登录后请改密码**）
- 串口：ttyAMA0 115200

## 后续

- `usbflash-debian11-wifi.zip`：在 v8 基础上替换了带驱动的内核
  （mt7601u / r8188eu / btusb 全部 built-in，由海思 SDK 编译），尚未实测
- 主线内核路线见 `docs/mainline.md`（histb-mainline 项目，Linux 7.4-rc4）
