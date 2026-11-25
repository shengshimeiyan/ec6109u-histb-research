# 华为悦盒 EC6109-U/M（Hi3798MV200）海纳思刷机研究

本仓库记录对华为悦盒 EC6109-U/M（Hi3798MV200 / 1G DDR3 / eMMC 4G / reg=mv2dma）刷入
海纳思（histb/ecoo.top）NAS 系统的完整逆向分析，重点是 **U 盘强刷包的板型适配原理**
与 **海思内核镜像格式**。

> 所有内容基于对官方刷机包的二进制逆向分析，仅用于技术研究与设备维护。

## 设备信息

| 项目 | 值 |
|---|---|
| 机型 | 华为悦盒 EC6109-U/M |
| SoC | HiSilicon Hi3798MV200（aarch64，4 核） |
| 内存 / 存储 | 1GB DDR3-1866 / eMMC 4GB |
| 板型 reg | `mv2dma`（DDR3-1866 1GB 16bitx2 2layers） |
| 短接点 | RN14 一端对地 |

## 核心成果

### 1. U 盘强刷的 DDR 适配（最重要）

官方 `mv200-mv2dmb-usb-flash-64.zip` 是 **mv2dmb / DDR4-2133 2GB** 板型的包，
直接刷到 mv2dma 板会黑屏。根因在根目录 `fastboot.bin`（BootROM 从 U 盘加载的引导）：

- `fastboot.bin` 内部固化了一份 **DDR 初始化配置表**（偏移 `0x4a0` 起，约 2.9KB）
- 原包该表声明 `hi3798mv2dmb_..._DDR4-2133_2GB`，与 mv2dma 的 DDR3-1GB 不匹配
- BootROM 用它初始化内存失败 → 代码无法运行 → 黑屏

**修复方法**：只替换 DDR 配置表，保留 U 盘强刷代码全部不变（文件尺寸不变）。

验证：原包 DDR 表与 TTL 包中 `fastboot-hi3798mv2dmb` 仅差 2 字节，
证明两处 DDR 表格式通用；替换为 `fastboot-hi3798mv2dma-6109u` 的表即可适配。

### 2. U-Boot 的 `run` 命令机制

作者在海思 U-Boot 中定制了 `run` 命令函数，`bootcmd=run flashfastboot; ...` 是
作者自创指令，逐个 `fatload usb` 读 `mv200/` 下的镜像并 `mmc write` 写入 eMMC。
**不需要 `usb start`**（U-Boot 初始化阶段已扫描 USB）。

### 3. 海思内核镜像格式（部分解析）

`hi_kernel.bin` 结构：

```
0x0 - 0x70a8       海思外层头（magic 0xaa640001 + 签名/长度字段）
                    0x48 = uImage 偏移 (0x70a8)
                    0x50 = uImage 总长
                    0x70 = 文件总长
0x70a8             uImage header (magic 0x27051956)
                    load/ep = 0x2000000, comp=0(未压缩)
                    hcrc 算法 = crc32(hdr64 with hcrc field zeroed)
0x70e8             payload = stub(重定位代码) + arm64 Image + DTB
                    DTB magic 0xd00dfeed，末尾 14314 字节
```

uImage header 的 CRC 算法（关键，算错会导致卡在刷机界面）：
```python
h = bytearray(header64); h[4:8] = b'\0\0\0\0'
hcrc = zlib.crc32(h) & 0xffffffff
```

> 注意：原内核 payload 内含海思自定义的解压/重定位 stub（多层），
> 且 stub 参数区在运行时由 BootROM 填充（文件内为 `0xffee` 填充），
> 因此**手工重建格式风险极高**。用裸 Image 直接替换 payload 即使 CRC 正确也无法启动。

### 4. 无线驱动的尝试与教训

- 系统自带 `/lib/modules/4.4.35_ecoo_81082668/` 下的 `.ko` **全是 32 位 ARMv7**，
  无法在 64 位内核加载（`Exec format error`）
- 用 aarch64 交叉编译器重新编译出 64 位模块（mt7601u/r8188eu/btusb），
  仅靠修改 `CONFIG_LOCALVERSION` 让 vermagic 匹配即可 insmod（内核未启用 MODVERSIONS）
- **但模块加载真硬件时内核 panic** —— 因为配置来自 defconfig 而非设备内核的精确 config，
  模块内部结构与实际内核不一致。惨痛教训：vermagic 匹配 ≠ ABI 匹配。
- 结论：要把驱动做进系统，必须**连内核一起替换**且配置完全一致；而 fnNAS 需要
  主线 6.x 内核，Hi3798MV200 无主线支持，此路不通。

## 刷机步骤（已验证成功）

1. U 盘：USB2.0、≤8G（4G 最稳）、FAT32 单分区、簇大小 2048
2. 把修正包的全部内容拷到 U 盘根目录，保持 `mv200/` 结构
3. **接网线**（盒子网口 → 路由器 LAN 口），教程说否则 99% 找不到 IP
4. 短接 RN14 → 保持短接上电 → **5 秒后放开短接**
5. 全程黑屏正常，等 5-8 分钟，不要断电
6. 出现"我是小盒子也是大世界"屏后再静置 5-8 分钟初始化
7. 路由器里找 MAC `00:11:22:33:44:55` 对应的 IP（默认 DHCP），浏览器访问进管理页

## 目录结构

```
README.md                     本文件
docs/flash-analysis.md        刷机包逐文件分析
docs/kernel-format.md         内核镜像格式详细解析
docs/wireless.md              无线驱动探索记录
tools/patch_firmware.py       生成 DDR 适配版 U 盘刷机包
tools/uimage_crc.py           uImage header CRC 计算/校验
files/                        小的关键二进制（bootargs.bin / fastboot 等）
```

## 大文件说明

刷机包 ZIP（300MB+）、内核源码（877MB）、rootfs 镜像（1.1GB）超过 GitHub 单文件
100MB 限制，未包含在仓库中。可从官方渠道获取：

- 官方固件：https://www.ecoo.top/download
- 适配表：https://www.ecoo.top/histb.html
- U 盘刷机教程：https://doc.ecoo.top/docs/tutorial-basics/usb-flash
- HiTool 工具：https://www.ecoo.top/hitool.html
