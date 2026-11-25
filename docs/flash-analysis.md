# 刷机包逐文件分析

## 两个官方包

### TTL 包：`TTL-hi3798mv200-64bit.zip`（579MB）

HiTool 烧写包，含金 XML 分区表：

```
fastboot    1M    0M     fastboot-hi3798mv2XXX-64.bin
bootargs    1M    1M     bootargs9-64.bin
baseparam   4M    2M
pqparam     4M    6M
logo        4M    10M
kernel     40M    14M    hi_kernel-mv200-64.bin
recovery   64M    54M    recoverybox64.ext4
backup     512M   118M   backup-64.ext4
rootfs      -     630M   rootfs-64.img (Ubuntu 20.04.5 arm64)
```

附带 18 种板型 fastboot（dma/dmb/dmc/dmd/dme/dmf/dmg/dmp），
XML 默认选 `dmg`，刷 EC6109-U 必须改成 `fastboot-hi3798mv2dma-6109u-64.bin`。

### U 盘包：`mv200-mv2dmb-usb-flash-64.zip`（305MB）

根目录 2 文件 + `mv200/` 子目录 8 文件：

| 文件 | 作用 |
|---|---|
| `fastboot.bin` (884224B) | BootROM 从 U 盘加载的强刷引导（多板型通用，含 6 套 DDR blob） |
| `bootargs.bin` (64KB) | 刷机命令环境：4 字节 CRC32 + `bootcmd=run flashfastboot; ...` |
| `mv200/fastboot.bin` | 写入 eMMC fastboot 分区（dmb DDR4-2G） |
| `mv200/bootargs.bin` | 写入 p2，日常启动 `root=/dev/mmcblk0p7`（先进 recovery） |
| `mv200/hi_kernel.bin` | 内核 |
| `mv200/baseparam.img`, `pq_param.bin`, `logo.img` | 显示参数 |
| `mv200/recoverybox64.ext4` | OpenWrt 恢复系统（p7） |
| `mv200/www_ecoo_top.ext4` | 备份分区，含 `backup-64.gz`（p8） |

## bootargs.bin 格式

- 前 4 字节：CRC32（小端），覆盖偏移 4 之后全部内容
- 之后是 `\0` 分隔的环境变量
- 修改 bootcmd 后必须重算 CRC，否则 fastboot 报 `bootargs crc failed`

histb 包 bootcmd（8 步刷机）：
```
usb start; run flashfastboot; run flashbootargs; run flashbase;
run flashpq; run flashlogo; run flashkernel; run flashrootfs;
run flashbackup; reset
```
（注：我曾在 bootcmd 前加 `usb start` 做过验证——教程说明作者 U-Boot 已支持，
实际上不需要；根因是 DDR 表。）

## DDR blob 位置（fastboot.bin）

```
0x4a0    头部默认 DDR 表（BootROM 初始化用）
0xcbe20  blob1 dmb DDR4-2G 2layers
0xcde20  blob2 dmb DDR4-2G 2layers
0xcfe20  blob3 dmc DDR4-2G 4layers
0xd3e20  blob4 dme DDR4-2G 8layers
0xd5e20  blob5 dmp DDR3-1G 2layers
```

每个 blob = 58 字节 reg 名 + 配置数据。原包 6 套里**没有 dma**。
只改头部 blob0 不够——U-Boot 可能运行时按板型 ID 从 0xcbe20 起重选，
因此最终成功方案是把 **6 套全部统一成 dma 参数**（来自
TTL 包 `fastboot-hi3798mv2dma-6109u-64.bin`，逐字节验证一致）。

## 恢复流程

刷完底包后盒子进 p7 的 OpenWrt recovery，`/etc/recovery.sh`：
1. 挂载 p8，把 `backup-64.gz` 解压 dd 到 p9（rootfs）
2. `resize2fs /dev/mmcblk0p9`
3. 把正确的 `bootargs9-64.bin`（root=p9）写回 p2
4. 写 logo 到 p5，reboot → 进 Ubuntu NAS

## 验证结果

- 成功刷入后系统：`Linux hi3798mv200 4.4.35_ecoo_82082668 aarch64`
- 服务：Web(80)/WebDAV(8081)/SSH(22)/FileBrowser(8680)/Samba/FTP/NFS/aria2/Transmission
- 默认 MAC：`00:11:22:33:44:55`
